from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.db import IntegrityError, transaction
from events.models import Event, TicketTier, Ticket, UserProfile, Venue, EmailVerification
from events.forms import (
    UserRegistrationForm,
    UserProfileForm,
    EventForm,
    TicketTierForm,
    ReviewForm,
)
from events.utils.khalti import KhaltiPayment
from django.db.models import F, Count, Sum, Avg
from django.db.models.functions import TruncDate, TruncMonth
import csv
import xlsxwriter
from django.utils import timezone
from datetime import timedelta
from django.utils.timesince import timesince
from django.urls import reverse
import logging
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def home(request):
    featured_events = Event.objects.filter(is_active=True, status="APPROVED").order_by("-created_at")[:6]
    return render(request, "events/home.html", {"featured_events": featured_events})


def register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match!')
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists!')
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered!')
            return redirect('register')

        # Create user but don't activate yet
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_active=False  # User will be activated after email verification
        )

        # Create email verification token
        token = EmailVerification.generate_token()
        verification = EmailVerification.objects.create(
            user=user,
            token=token
        )

        # Generate verification URL
        verification_url = request.build_absolute_uri(
            f'/verify-email/{token}/'
        )

        # Send verification email
        context = {
            'user': user,
            'verification_url': verification_url
        }
        html_message = render_to_string('emails/verify_email.html', context)
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject='Verify your email address',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False,
            )
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('login')
        except Exception as e:
            # If email sending fails, delete the user and verification
            user.delete()
            messages.error(request, 'Failed to send verification email. Please try again.')
            return redirect('register')

    return render(request, 'registration/register.html')


def verify_email(request, token):
    try:
        verification = EmailVerification.objects.get(token=token)
        
        # Check if token is expired (24 hours)
        if timezone.now() - verification.created_at > timedelta(hours=24):
            messages.error(request, 'Verification link has expired. Please register again.')
            verification.user.delete()
            return redirect('register')
        
        # Activate user
        user = verification.user
        user.is_active = True
        user.save()
        
        # Mark verification as complete
        verification.is_verified = True
        verification.save()
        
        messages.success(request, 'Email verified successfully! You can now login.')
        return redirect('login')
    except EmailVerification.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
        return redirect('register')


@login_required
def profile(request):
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect("profile")
    else:
        form = UserProfileForm(instance=profile)

    return render(request, "events/profile.html", {"form": form})


def event_list(request):
    # Start with ordered queryset, only showing approved events
    events = Event.objects.filter(is_active=True, status="APPROVED").order_by("-date", "-time", "title")

    # Search functionality
    query = request.GET.get("q")
    if query:
        events = events.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(category__icontains=query)
        )

    # Category filter
    category = request.GET.get("category")
    if category:
        events = events.filter(category=category)

    # Pagination
    paginator = Paginator(events, 12)
    page = request.GET.get("page")
    events = paginator.get_page(page)

    return render(request, "events/event_list.html", {"events": events})


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    ticket_tiers = event.ticket_tiers.all()
    reviews = event.reviews.all().order_by("-created_at")

    if request.method == "POST" and request.user.is_authenticated:
        review_form = ReviewForm(request.POST)
        if review_form.is_valid():
            review = review_form.save(commit=False)
            review.event = event
            review.user = request.user
            review.save()
            messages.success(request, "Review submitted successfully!")
            return redirect("event_detail", event_id=event.id)
    else:
        review_form = ReviewForm()

    context = {
        "event": event,
        "ticket_tiers": ticket_tiers,
        "reviews": reviews,
        "review_form": review_form,
    }
    return render(request, "events/event_detail.html", context)


def send_event_notification_email(request, event):
    """Send notification email to all users about a new event"""
    from django.contrib.auth.models import User
    from django.urls import reverse

    # Get all users
    users = User.objects.filter(is_active=True)

    # Format dates and times properly
    event_date = event.date.strftime("%B %d, %Y")  # e.g. "January 01, 2023"
    event_time = event.time.strftime("%I:%M %p")  # e.g. "02:30 PM"

    # Prepare event data for email
    event_data = {
        "title": event.title,
        "category": event.get_category_display(),
        "date": event_date,
        "time": event_time,
        "venue": event.venue,
        "description": event.description,
    }

    # Get the event URL
    event_url = request.build_absolute_uri(
        reverse("event_detail", kwargs={"event_id": event.id})
    )

    subject = f"New Event: {event.title}"

    for user in users:
        context = {"user": user, "event": event_data, "event_url": event_url}

        html_message = render_to_string("emails/new_event_notification.html", context)
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
                fail_silently=True,  # Don't fail if one email fails
            )
        except Exception as e:
            print(f"Failed to send event notification email to {user.email}: {str(e)}")


@login_required
def create_event(request):
    if request.method == "POST":
        event_form = EventForm(request.POST, request.FILES)
        if event_form.is_valid():
            event = event_form.save(commit=False)
            event.organizer = request.user
            event.status = "PENDING"  # Set initial status as pending
            event.save()

            messages.success(
                request, 
                "Your event has been submitted for approval. You will be notified once it's approved."
            )
            return redirect("organizer_dashboard")
    else:
        event_form = EventForm()

    # Get available venues for the form
    available_venues = Venue.objects.filter(is_available=True)
    
    return render(request, "events/create_event.html", {
        "form": event_form,
        "available_venues": available_venues
    })


@login_required
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Event updated successfully!")
            return redirect("event_detail", event_id=event.id)
    else:
        form = EventForm(instance=event)

    return render(request, "events/edit_event.html", {"form": form, "event": event})


@login_required
def create_ticket_tier(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)

    if request.method == "POST":
        form = TicketTierForm(request.POST)
        if form.is_valid():
            ticket_tier = form.save(commit=False)
            ticket_tier.event = event
            ticket_tier.sold_quantity = 0  # Initialize sold_quantity to 0
            ticket_tier.save()
            messages.success(request, "Ticket tier created successfully!")
            return redirect("event_detail", event_id=event.id)
    else:
        form = TicketTierForm()

    return render(
        request, "events/create_ticket_tier.html", {"form": form, "event": event}
    )


@login_required
def purchase_ticket(request, tier_id):
    ticket_tier = get_object_or_404(TicketTier, id=tier_id)

    if request.method == "POST":
        quantity = int(request.POST.get("quantity", 1))
        payment_method = request.POST.get("payment_method", "KHALTI")

        # Validate quantity
        if quantity <= 0 or quantity > ticket_tier.available_tickets:
            messages.error(request, "Invalid quantity selected.")
            return redirect("event_detail", event_id=ticket_tier.event.id)

        try:
            # Create ticket (initially with PENDING status)
            ticket = Ticket.objects.create(
                tier=ticket_tier,
                user=request.user,
                status="PENDING",
                quantity=quantity,
                payment_method=payment_method,
            )

            if payment_method == "KHALTI":
                payment_data = KhaltiPayment.initiate_payment(
                    request, ticket, "verify_payment"
                )

                ticket.payment_id = payment_data.get("pidx", "")
                ticket.save()

                return redirect(payment_data["payment_url"])
            else:  # Cash payment
                # For cash payments, we'll create the ticket but keep it as PENDING
                # until verified by the organizer
                messages.success(
                    request,
                    "Your ticket request has been received. "
                    "Please pay cash to the organizer and they will verify your payment.",
                )
                return redirect("event_detail", event_id=ticket_tier.event.id)

        except Exception as e:
            if "ticket" in locals():
                ticket.delete()
            messages.error(request, str(e))
            return redirect("event_detail", event_id=ticket_tier.event.id)

    return render(
        request,
        "events/purchase_ticket.html",
        {
            "ticket_tier": ticket_tier,
            "khalti_public_key": settings.KHALTI_PUBLIC_KEY,
        },
    )


@login_required
def verify_cash_payment(request, ticket_id):
    """View for organizers to verify cash payments"""
    ticket = get_object_or_404(Ticket, id=ticket_id)

    # Only event organizers can verify tickets
    if request.user != ticket.tier.event.organizer:
        messages.error(
            request, "You do not have permission to verify tickets for this event."
        )
        return redirect("event_detail", event_id=ticket.tier.event.id)

    if request.method == "POST":
        if ticket.verify_cash_payment(request.user):
            messages.success(request, "Cash payment verified and ticket confirmed!")
            # Send confirmation email
            send_ticket_confirmation_email(request, ticket)
        else:
            messages.error(request, "Could not verify cash payment. Please try again.")

        return redirect("manage_attendees", event_id=ticket.tier.event.id)

    return render(request, "events/verify_cash_payment.html", {"ticket": ticket})


@login_required
def my_tickets(request):
    tickets = Ticket.objects.filter(user=request.user).order_by("-purchase_date")

    # Get filter parameters
    status_filter = request.GET.get("status", "")

    # Apply filters if provided
    if status_filter:
        tickets = tickets.filter(status__in=status_filter.split(","))

    # Separate tickets by status for better display
    pending_tickets = tickets.filter(status="PENDING", payment_method="CASH")
    confirmed_tickets = tickets.filter(status="SOLD")
    other_tickets = tickets.exclude(status="PENDING", payment_method="CASH").exclude(
        status="SOLD"
    )

    return render(
        request,
        "events/my_tickets.html",
        {
            "tickets": tickets,
            "pending_tickets": pending_tickets,
            "confirmed_tickets": confirmed_tickets,
            "other_tickets": other_tickets,
        },
    )


@login_required
def verify_payment(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user)
    pidx = request.GET.get("pidx") or ticket.payment_id

    if not pidx:
        messages.error(request, "Invalid payment verification request.")
        return redirect("event_detail", event_id=ticket.tier.event.id)

    try:
        verification = KhaltiPayment.verify_payment(pidx)

        if verification.get("status") == "Completed":
            if not ticket.tier.decrease_available_tickets(ticket.quantity):
                messages.error(request, "Sorry, not enough tickets available now.")
                ticket.status = "CANCELLED"
                ticket.save()
                return redirect("event_detail", event_id=ticket.tier.event.id)
            ticket.status = "SOLD"
            ticket.payment_id = pidx
            ticket.save()

            # Send confirmation email
            send_ticket_confirmation_email(request, ticket)

            messages.success(
                request, "Payment successful! Your ticket has been confirmed."
            )
            return redirect("my_tickets")
        else:
            ticket.status = "CANCELLED"
            ticket.save()
            messages.error(
                request,
                f'Payment verification failed. Status: {verification.get("status")}',
            )

    except Exception as e:
        messages.error(request, str(e))

    return redirect("event_detail", event_id=ticket.tier.event.id)


def send_ticket_confirmation_email(request, ticket):
    """Send ticket confirmation email with all details"""
    subject = f"Ticket Confirmation - {ticket.tier.event.title}"

    # Format dates and times properly
    event_date = ticket.tier.event.date.strftime("%B %d, %Y")  # e.g. "January 01, 2023"
    event_time = ticket.tier.event.time.strftime("%I:%M %p")  # e.g. "02:30 PM"

    context = {
        "user": request.user,
        "event": {
            "title": ticket.tier.event.title,
            "date": event_date,
            "time": event_time,
            "venue": ticket.tier.event.venue,
        },
        "tier_name": ticket.tier.name,
        "quantity": ticket.quantity,
        "total_price": ticket.get_total_price(),
        "my_tickets_url": request.build_absolute_uri(reverse("my_tickets")),
    }

    html_message = render_to_string("emails/ticket_confirmation.html", context)
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            html_message=html_message,
        )
    except Exception as e:
        logger.error(f"Failed to send ticket confirmation email: {str(e)}")


@login_required
def download_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user)
    return render(request, "events/download_ticket.html", {"ticket": ticket})


@login_required
def verify_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)

    # Only event organizers can verify tickets
    if request.user != ticket.tier.event.organizer:
        messages.error(
            request, "You do not have permission to verify tickets for this event."
        )
        return redirect("event_detail", event_id=ticket.tier.event.id)

    # Check if ticket is valid
    if ticket.status != "SOLD":
        messages.error(request, "This ticket is not valid for entry.")
        return render(
            request,
            "events/verify_ticket.html",
            {
                "ticket": ticket,
                "is_valid": False,
                "reason": f"Ticket status is {ticket.status}",
            },
        )

    # Check if ticket has already been used
    if ticket.status == "USED":
        messages.error(request, "This ticket has already been used.")
        return render(
            request,
            "events/verify_ticket.html",
            {
                "ticket": ticket,
                "is_valid": False,
                "reason": "Ticket has already been used",
            },
        )

    # Check if event date is valid
    if ticket.tier.event.is_past_event:
        messages.error(request, "This event has already passed.")
        return render(
            request,
            "events/verify_ticket.html",
            {"ticket": ticket, "is_valid": False, "reason": "Event has already passed"},
        )

    if request.method == "POST":
        # Mark ticket as used and record check-in time
        if ticket.check_in():
            messages.success(
                request, "Ticket successfully verified and marked as used."
            )
            return redirect("checkin_dashboard", event_id=ticket.tier.event.id)
        else:
            messages.error(request, "Failed to check in ticket. Please try again.")

    return render(
        request, "events/verify_ticket.html", {"ticket": ticket, "is_valid": True}
    )


@login_required
def scan_ticket(request):
    """View for scanning QR codes"""
    return render(request, "events/scan_ticket.html")


@login_required
def manage_attendees(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    tickets = Ticket.objects.filter(tier__event=event).select_related("user", "tier")

    # Get check-in statistics
    stats = {
        "total": tickets.count(),
        "checked_in": tickets.filter(status="USED").count(),
        "pending": tickets.filter(status="SOLD").count(),
    }

    # Handle export requests
    if "export" in request.GET:
        export_format = request.GET.get("export")
        if export_format == "csv":
            return export_attendees_csv(tickets, event)
        elif export_format == "excel":
            return export_attendees_excel(tickets, event)

    return render(
        request,
        "events/manage_attendees.html",
        {
            "event": event,
            "tickets": tickets,
            "stats": stats,
        },
    )


def export_attendees_csv(tickets, event):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{event.title}_attendees_{timezone.now().strftime("%Y%m%d")}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(
        [
            "Ticket ID",
            "Attendee Name",
            "Email",
            "Ticket Type",
            "Purchase Date",
            "Check-in Status",
        ]
    )

    for ticket in tickets:
        writer.writerow(
            [
                ticket.id,
                ticket.user.get_full_name() or ticket.user.username,
                ticket.user.email,
                ticket.tier.name,
                ticket.purchase_date.strftime("%Y-%m-%d %H:%M:%S"),
                ticket.status,
            ]
        )

    return response


def export_attendees_excel(tickets, event):
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{event.title}_attendees_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    )

    workbook = xlsxwriter.Workbook(response, {"in_memory": True})
    worksheet = workbook.add_worksheet()

    headers = [
        "Ticket ID",
        "Attendee Name",
        "Email",
        "Ticket Type",
        "Purchase Date",
        "Check-in Status",
    ]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)

    for row, ticket in enumerate(tickets, start=1):
        worksheet.write(row, 0, ticket.id)
        worksheet.write(row, 1, ticket.user.get_full_name() or ticket.user.username)
        worksheet.write(row, 2, ticket.user.email)
        worksheet.write(row, 3, ticket.tier.name)
        worksheet.write(row, 4, ticket.purchase_date.strftime("%Y-%m-%d %H:%M:%S"))
        worksheet.write(row, 5, ticket.status)

    workbook.close()
    return response


@login_required
def checkin_dashboard(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    tickets = Ticket.objects.filter(tier__event=event)
    stats = {
        "total_tickets": tickets.count(),
        "checked_in": tickets.filter(status="USED").count(),
        "pending": tickets.filter(status="SOLD").count(),
        "by_tier": tickets.values("tier__name").annotate(
            total=Count("id"), checked_in=Count("id", filter=Q(status="USED"))
        ),
    }

    recent_checkins = tickets.filter(status="USED").order_by("-updated_at")[:10]

    return render(
        request,
        "events/checkin_dashboard.html",
        {
            "event": event,
            "stats": stats,
            "recent_checkins": recent_checkins,
        },
    )


@login_required
def checkin_stats(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    tickets = Ticket.objects.filter(tier__event=event)
    stats = {
        "total_tickets": tickets.count(),
        "checked_in": tickets.filter(status="USED").count(),
        "pending": tickets.filter(status="SOLD").count(),
    }

    recent_checkins = tickets.filter(status="USED").order_by("-check_in_time")[:10]
    recent_checkins_data = [
        {
            "user_name": checkin.user.get_full_name() or checkin.user.username,
            "tier_name": checkin.tier.name,
            "time_ago": timesince(checkin.check_in_time),
        }
        for checkin in recent_checkins
    ]

    stats["recent_checkins"] = recent_checkins_data

    return JsonResponse(stats)


@login_required
def organizer_dashboard(request):
    """Dashboard for event organizers with analytics and management tools"""

    events = Event.objects.filter(organizer=request.user)

    total_events = events.count()
    active_events = events.filter(is_active=True).count()

    total_tickets = (
        Ticket.objects.filter(
            tier__event__organizer=request.user, status="SOLD"
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    total_revenue = (
        Ticket.objects.filter(
            tier__event__organizer=request.user, status="SOLD"
        ).aggregate(total=Sum(F("tier__price") * F("quantity")))["total"]
        or 0
    )

    event_sales = events.annotate(
        tickets_sold=Sum(
            "ticket_tiers__tickets__quantity",
            filter=Q(ticket_tiers__tickets__status="SOLD"),
        ),
        revenue=Sum(
            F("ticket_tiers__tickets__tier__price")
            * F("ticket_tiers__tickets__quantity"),
            filter=Q(ticket_tiers__tickets__status="SOLD"),
        ),
    )
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_sales = (
        Ticket.objects.filter(
            tier__event__organizer=request.user,
            status="SOLD",
            purchase_date__gte=thirty_days_ago,
        )
        .annotate(date=TruncDate("purchase_date"))
        .values("date")
        .annotate(count=Sum("quantity"), revenue=Sum(F("tier__price") * F("quantity")))
        .order_by("date")
    )

    monthly_revenue = (
        Ticket.objects.filter(tier__event__organizer=request.user, status="SOLD")
        .annotate(month=TruncMonth("purchase_date"))
        .values("month")
        .annotate(revenue=Sum(F("tier__price") * F("quantity")))
        .order_by("month")
    )
    ticket_types = (
        TicketTier.objects.filter(event__organizer=request.user)
        .values("name")
        .annotate(
            count=Sum("tickets__quantity", filter=Q(tickets__status="SOLD")),
            revenue=Sum(
                F("tickets__tier__price") * F("tickets__quantity"),
                filter=Q(tickets__status="SOLD"),
            ),
        )
    )
    recent_transactions = (
        Ticket.objects.filter(tier__event__organizer=request.user, status="SOLD")
        .select_related("user", "tier", "tier__event")
        .order_by("-purchase_date")[:10]
    )

    upcoming_events = events.filter(
        date__gte=timezone.now().date(), is_active=True
    ).order_by("date")[:5]

    context = {
        "total_events": total_events,
        "active_events": active_events,
        "total_tickets": total_tickets,
        "total_revenue": total_revenue,
        "event_sales": event_sales,
        "daily_sales": daily_sales,
        "monthly_revenue": monthly_revenue,
        "ticket_types": ticket_types,
        "recent_transactions": recent_transactions,
        "upcoming_events": upcoming_events,
    }

    return render(request, "events/organizer_dashboard.html", context)


@login_required
def event_analytics(request, event_id):
    """Detailed analytics for a specific event"""

    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    ticket_stats = Ticket.objects.filter(tier__event=event).aggregate(
        total_sold=Count("id", filter=Q(status="SOLD")),
        total_revenue=Sum("tier__price", filter=Q(status="SOLD")),
        avg_price=Avg("tier__price", filter=Q(status="SOLD")),
    )

    tier_sales = TicketTier.objects.filter(event=event).annotate(
        sold=Count("tickets", filter=Q(tickets__status="SOLD")),
        revenue=Sum("tickets__tier__price", filter=Q(tickets__status="SOLD")),
    )
    daily_sales = (
        Ticket.objects.filter(tier__event=event, status="SOLD")
        .annotate(date=TruncDate("purchase_date"))
        .values("date")
        .annotate(count=Count("id"), revenue=Sum("tier__price"))
        .order_by("date")
    )
    checkin_stats = Ticket.objects.filter(tier__event=event).aggregate(
        total_checked=Count("id", filter=Q(status="USED")),
        pending_checkin=Count("id", filter=Q(status="SOLD")),
    )

    context = {
        "event": event,
        "ticket_stats": ticket_stats,
        "tier_sales": tier_sales,
        "daily_sales": daily_sales,
        "checkin_stats": checkin_stats,
    }

    return render(request, "events/event_analytics.html", context)


@login_required
def update_event_status(request, event_id):
    """View to handle event status updates (approve/reject)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    event = get_object_or_404(Event, id=event_id)
    action = request.POST.get('action')
    admin_notes = request.POST.get('admin_notes', '')
    suggested_venues = request.POST.getlist('suggested_venues[]')  # Get list of suggested venue IDs

    if action not in ['APPROVED', 'REJECTED']:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    try:
        if action == 'APPROVED':
            # Update event status
            event.status = 'APPROVED'
            event.is_active = True
            event.save()
            
            # Send approval email to event organizer
            subject = f"Your Event '{event.title}' Has Been Approved!"
            
            # Format dates and times properly
            event_date = event.date.strftime("%B %d, %Y")
            event_time = event.time.strftime("%I:%M %p")
            
            context = {
                'user': event.organizer,
                'event': {
                    'title': event.title,
                    'date': event_date,
                    'time': event_time,
                    'venue': event.venue,
                    'description': event.description,
                },
                'admin_notes': admin_notes,
                'event_url': request.build_absolute_uri(
                    reverse('event_detail', kwargs={'event_id': event.id})
                ),
                'dashboard_url': request.build_absolute_uri(
                    reverse('organizer_dashboard')
                )
            }
            
            html_message = render_to_string('emails/event_approval.html', context)
            plain_message = strip_tags(html_message)
            
            try:
                send_mail(
                    subject,
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [event.organizer.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                logger.info(f"Approval email sent to {event.organizer.email} for event {event.title}")
            except Exception as e:
                logger.error(f"Failed to send event approval email to {event.organizer.email}: {str(e)}")
                # Continue with the approval process even if email fails
                
        else:  # REJECTED
            # Update event status
            event.status = 'REJECTED'
            event.is_active = False
            event.save()
            
            # Get all active venues for suggestions
            all_venues = Venue.objects.filter(is_active=True)
            
            # If specific venues were suggested, prioritize them
            suggested_venues_data = []
            if suggested_venues:
                # Get the suggested venues first
                suggested = all_venues.filter(id__in=suggested_venues)
                suggested_venues_data.extend([{
                    'name': venue.name,
                    'capacity': venue.capacity,
                    'address': venue.address,
                    'description': venue.description,
                    'is_suggested': True
                } for venue in suggested])
                
                # Add other venues that weren't suggested
                other_venues = all_venues.exclude(id__in=suggested_venues)
                suggested_venues_data.extend([{
                    'name': venue.name,
                    'capacity': venue.capacity,
                    'address': venue.address,
                    'description': venue.description,
                    'is_suggested': False
                } for venue in other_venues])
            else:
                # If no specific venues were suggested, include all venues
                suggested_venues_data = [{
                    'name': venue.name,
                    'capacity': venue.capacity,
                    'address': venue.address,
                    'description': venue.description,
                    'is_suggested': False
                } for venue in all_venues]
            
            # Send rejection email to event organizer
            subject = f"Your Event '{event.title}' Has Been Rejected"
            
            context = {
                'user': event.organizer,
                'event': {
                    'title': event.title,
                    'date': event.date.strftime("%B %d, %Y"),
                    'time': event.time.strftime("%I:%M %p"),
                },
                'admin_notes': admin_notes,
                'suggested_venues': suggested_venues_data,
                'dashboard_url': request.build_absolute_uri(
                    reverse('organizer_dashboard')
                )
            }
            
            html_message = render_to_string('emails/event_rejection.html', context)
            plain_message = strip_tags(html_message)
            
            try:
                send_mail(
                    subject,
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [event.organizer.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                logger.info(f"Rejection email sent to {event.organizer.email} for event {event.title}")
            except Exception as e:
                logger.error(f"Failed to send event rejection email to {event.organizer.email}: {str(e)}")
                # Continue with the rejection process even if email fails
        
        return JsonResponse({'message': f'Event {action.lower()} successfully'})
    except Exception as e:
        logger.error(f"Error updating event status: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_available_venues(request):
    """Get a list of available venues based on date and capacity"""
    date = request.GET.get('date')
    capacity = request.GET.get('capacity')
    
    if not date:
        return JsonResponse({'error': 'Date is required'}, status=400)
    
    try:
        # Convert date string to datetime object
        event_date = timezone.datetime.strptime(date, '%Y-%m-%d').date()
        
        # Get venues that are not booked for the given date
        booked_venues = Event.objects.filter(
            date=event_date,
            is_active=True
        ).values_list('venue', flat=True)
        
        # Query available venues
        venues = Venue.objects.filter(is_active=True).exclude(id__in=booked_venues)
        
        # Filter by capacity if provided
        if capacity:
            venues = venues.filter(capacity__gte=int(capacity))
        
        # Prepare venue data
        venue_data = [{
            'id': venue.id,
            'name': venue.name,
            'address': venue.address,
            'capacity': venue.capacity,
            'description': venue.description
        } for venue in venues]
        
        return JsonResponse({'venues': venue_data})
        
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def check_venue_availability(request):
    """Check if a specific venue is available on a given date"""
    venue = request.GET.get('venue')
    date = request.GET.get('date')
    
    if not venue or not date:
        return JsonResponse({
            'error': 'Both venue and date are required'
        }, status=400)
    
    try:
        # Convert date string to datetime object
        event_date = timezone.datetime.strptime(date, '%Y-%m-%d').date()
        
        # Check if venue exists
        venue = get_object_or_404(Venue, id=venue)
        
        # Check if venue is booked for the given date
        is_booked = Event.objects.filter(
            venue=venue,
            date=event_date,
            is_active=True
        ).exists()
        
        return JsonResponse({
            'venue': venue,
            'date': date,
            'is_available': not is_booked,
            'venue_details': {
                'name': venue.name,
                'capacity': venue.capacity,
                'address': venue.address
            }
        })
        
    except ValueError:
        return JsonResponse({
            'error': 'Invalid date format. Use YYYY-MM-DD'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

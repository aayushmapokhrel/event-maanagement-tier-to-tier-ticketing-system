from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Sum, F
from django.utils import timezone
from datetime import timedelta
from .models import Event, Ticket, Review, User, Venue, TicketTier
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
import json
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib import messages
import os
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.urls import reverse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect
from events.forms import EventAdminForm


@staff_member_required
def admin_dashboard(request):
    # Get statistics
    total_users = User.objects.count()
    active_events = Event.objects.filter(date__gte=timezone.now()).count()

    # Get total tickets sold (considering quantity)
    tickets_sold = (
        Ticket.objects.filter(status="SOLD").aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    # Calculate total revenue (price * quantity)
    total_revenue = (
        Ticket.objects.filter(status="SOLD")
        .select_related("tier")
        .aggregate(total=Sum(F("tier__price") * F("quantity")))["total"]
        or 0
    )

    # Get revenue data for the last 7 days
    last_7_days = [(timezone.now() - timedelta(days=i)).date() for i in range(7)]
    revenue_data = []
    revenue_labels = []

    for date in reversed(last_7_days):
        daily_revenue = (
            Ticket.objects.filter(purchase_date__date=date, status="SOLD")
            .select_related("tier")
            .aggregate(total=Sum(F("tier__price") * F("quantity")))["total"]
            or 0
        )
        revenue_data.append(float(daily_revenue))
        revenue_labels.append(date.strftime("%b %d"))

    # Get event categories distribution
    categories = (
        Event.objects.values("category").annotate(count=Count("id")).order_by("-count")
    )
    category_labels = [cat["category"] for cat in categories]
    category_data = [cat["count"] for cat in categories]

    # Get recent activities
    recent_activities = []

    # Recent ticket purchases
    recent_tickets = Ticket.objects.select_related(
        "user", "tier", "tier__event"
    ).order_by("-purchase_date")[:5]
    for ticket in recent_tickets:
        recent_activities.append(
            {
                "description": f"{ticket.quantity} ticket(s) purchased for {ticket.tier.event.title} ({ticket.tier.name})",
                "user": ticket.user.username,
                "date": ticket.purchase_date,
                "status": "Completed",
                "status_color": "success",
            }
        )

    # Recent events created
    recent_events = Event.objects.select_related("organizer").order_by("-created_at")[
        :5
    ]
    for event in recent_events:
        recent_activities.append(
            {
                "description": f"New event created: {event.title}",
                "user": event.organizer.username,
                "date": event.created_at,
                "status": "Active" if event.date >= timezone.now().date() else "Past",
                "status_color": (
                    "primary" if event.date >= timezone.now().date() else "secondary"
                ),
            }
        )

    # Sort activities by date
    recent_activities.sort(key=lambda x: x["date"], reverse=True)
    recent_activities = recent_activities[:10]

    # Convert data to JSON-safe format
    context = {
        "total_users": total_users,
        "active_events": active_events,
        "tickets_sold": tickets_sold,
        "total_revenue": total_revenue,
        "revenue_data": json.dumps(revenue_data),
        "revenue_labels": json.dumps(revenue_labels),
        "category_labels": json.dumps(category_labels),
        "category_data": json.dumps(category_data),
        "recent_activities": recent_activities,
    }

    return render(request, "admin_dashboard/dashboard.html", context)


@staff_member_required
def admin_users(request):
    users = User.objects.select_related("userprofile").all()
    return render(request, "admin_dashboard/users.html", {"users": users})


def is_admin(user):
    return user.is_staff


@login_required
@user_passes_test(is_admin)
def admin_events(request):
    events = Event.objects.all().order_by('-created_at')
    # Get only available venues
    venues = Venue.objects.filter(is_available=True)
    return render(request, 'admin_dashboard/events.html', {
        'events': events,
        'venues': venues
    })


@staff_member_required
def admin_tickets(request):
    tickets = Ticket.objects.select_related("user", "tier", "tier__event").all()
    return render(request, "admin_dashboard/tickets.html", {"tickets": tickets})


@staff_member_required
def admin_reviews(request):
    reviews = Review.objects.select_related("user", "event").all()
    return render(request, "admin_dashboard/reviews.html", {"reviews": reviews})


@staff_member_required
def admin_payments(request):
    payments = (
        Ticket.objects.select_related("user", "tier", "tier__event")
        .filter(status="SOLD")
        .order_by("-purchase_date")
    )
    return render(request, "admin_dashboard/payments.html", {"payments": payments})


@staff_member_required
def admin_settings(request):
    # Get current settings
    settings = {
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": os.getenv("SMTP_PORT", "587"),
        "from_email": os.getenv("FROM_EMAIL", ""),
        "currency": os.getenv("CURRENCY", "INR"),
        "payment_gateway": os.getenv("PAYMENT_GATEWAY", "razorpay"),
        "api_key": os.getenv("PAYMENT_API_KEY", ""),
        "site_name": os.getenv("SITE_NAME", "Event Management System"),
        "contact_email": os.getenv("CONTACT_EMAIL", ""),
        "support_phone": os.getenv("SUPPORT_PHONE", ""),
        "maintenance_mode": os.getenv("MAINTENANCE_MODE", "False").lower() == "true",
        "email_notifications": os.getenv("EMAIL_NOTIFICATIONS", "True").lower()
        == "true",
        "sms_notifications": os.getenv("SMS_NOTIFICATIONS", "False").lower() == "true",
        "sms_api_key": os.getenv("SMS_API_KEY", ""),
    }
    return render(request, "admin_dashboard/settings.html", settings)


@staff_member_required
@require_POST
def update_email_settings(request):
    try:
        # Update email settings in environment variables or settings file
        os.environ["SMTP_HOST"] = request.POST.get("smtp_host", "")
        os.environ["SMTP_PORT"] = request.POST.get("smtp_port", "587")
        os.environ["FROM_EMAIL"] = request.POST.get("from_email", "")

        # You might want to persist these settings in a configuration file
        # For now, we'll just update the environment variables

        return JsonResponse(
            {"success": True, "message": "Email settings updated successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_POST
def update_payment_settings(request):
    try:
        os.environ["CURRENCY"] = request.POST.get("currency", "INR")
        os.environ["PAYMENT_GATEWAY"] = request.POST.get("payment_gateway", "razorpay")
        os.environ["PAYMENT_API_KEY"] = request.POST.get("api_key", "")

        return JsonResponse(
            {"success": True, "message": "Payment settings updated successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_POST
def update_general_settings(request):
    try:
        os.environ["SITE_NAME"] = request.POST.get(
            "site_name", "Event Management System"
        )
        os.environ["CONTACT_EMAIL"] = request.POST.get("contact_email", "")
        os.environ["SUPPORT_PHONE"] = request.POST.get("support_phone", "")
        os.environ["MAINTENANCE_MODE"] = str(
            request.POST.get("maintenance_mode", "false")
        ).lower()

        return JsonResponse(
            {"success": True, "message": "General settings updated successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_POST
def update_notification_settings(request):
    try:
        os.environ["EMAIL_NOTIFICATIONS"] = str(
            request.POST.get("email_notifications", "true")
        ).lower()
        os.environ["SMS_NOTIFICATIONS"] = str(
            request.POST.get("sms_notifications", "false")
        ).lower()
        os.environ["SMS_API_KEY"] = request.POST.get("sms_api_key", "")

        return JsonResponse(
            {"success": True, "message": "Notification settings updated successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_POST
def add_user(request):
    try:
        data = json.loads(request.body)
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role")

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create_user(
            username=username, email=email, password=password
        )

        if role == "staff":
            user.is_staff = True
        elif role == "admin":
            user.is_staff = True
            user.is_superuser = True

        user.save()

        return JsonResponse({"message": "User created successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def update_user(request, user_id):
    try:
        user = get_object_or_404(User, id=user_id)
        data = json.loads(request.body)

        user.email = data.get("email", user.email)
        if data.get("password"):
            user.set_password(data["password"])

        role = data.get("role")
        if role == "staff":
            user.is_staff = True
            user.is_superuser = False
        elif role == "admin":
            user.is_staff = True
            user.is_superuser = True
        elif role == "user":
            user.is_staff = False
            user.is_superuser = False

        user.save()
        return JsonResponse({"message": "User updated successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def toggle_user_status(request, user_id):
    try:
        user = get_object_or_404(User, id=user_id)
        user.is_active = not user.is_active
        user.save()
        return JsonResponse(
            {
                "message": f'User {"activated" if user.is_active else "deactivated"} successfully',
                "status": user.is_active,
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def delete_user(request, user_id):
    try:
        user = get_object_or_404(User, id=user_id)
        user.delete()
        return JsonResponse({"message": "User deleted successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)



@login_required
@user_passes_test(is_admin)
def delete_event(request, event_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    event = get_object_or_404(Event, id=event_id)
    
    try:
        event.delete()
        return JsonResponse({'message': 'Event deleted successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
def event_tickets(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    tickets = Ticket.objects.filter(tier__event=event).select_related("user", "tier")
    return render(
        request,
        "admin_dashboard/event_tickets.html",
        {"event": event, "tickets": tickets},
    )


@staff_member_required
@require_GET
def get_ticket_details(request, ticket_id):
    try:
        ticket = get_object_or_404(Ticket, id=ticket_id)
        ticket_data = {
            "id": ticket.id,
            "tier": {
                "name": ticket.tier.name,
                "price": float(ticket.tier.price),
                "event": {"title": ticket.tier.event.title},
            },
            "user": {"username": ticket.user.username},
            "purchase_date": ticket.purchase_date.isoformat(),
            "status": ticket.status,
        }
        return JsonResponse(ticket_data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def resend_ticket(request, ticket_id):
    """Resend ticket details to the user via email"""
    try:
        ticket = get_object_or_404(Ticket, id=ticket_id)

        # Format dates and times properly
        event_date = ticket.tier.event.date.strftime(
            "%B %d, %Y"
        )  # e.g. "January 01, 2023"
        event_time = ticket.tier.event.time.strftime("%I:%M %p")

        context = {
            "user": ticket.user,
            "event": {
                "title": ticket.tier.event.title,
                "date": event_date,
                "time": event_time,
                "venue": ticket.tier.event.venue,
            },
            "tier_name": ticket.tier.name,
            "quantity": ticket.quantity,
            "total_price": ticket.get_total_price(),
            "my_tickets_url": request.build_absolute_uri(
                "/my-tickets/"
            ),  # Adjust this URL as needed
        }

        # Render email template
        html_message = render_to_string("emails/ticket_confirmation.html", context)
        plain_message = strip_tags(html_message)

        # Send email
        send_mail(
            subject=f"Ticket Details - {ticket.tier.event.title}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.user.email],
            html_message=html_message,
        )

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@staff_member_required
@require_POST
def cancel_ticket(request, ticket_id):
    try:
        ticket = get_object_or_404(Ticket, id=ticket_id)

        if ticket.status != "PENDING":
            return JsonResponse(
                {"success": False, "error": "Only pending tickets can be cancelled"},
                status=400,
            )

        ticket.status = "CANCELLED"
        ticket.save()

        # Send cancellation email
        subject = f"Ticket Cancellation - {ticket.tier.event.title}"
        html_message = render_to_string(
            "emails/ticket_cancellation.html", {"ticket": ticket}
        )
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [ticket.user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            # Log email sending error but don't fail the transaction
            print(f"Error sending cancellation email: {str(e)}")

        return JsonResponse(
            {"success": True, "message": "Ticket cancelled successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_GET
def get_review_details(request, review_id):
    try:
        review = get_object_or_404(Review, id=review_id)
        review_data = {
            "id": review.id,
            "event": {"title": review.event.title},
            "user": {"username": review.user.username},
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at.isoformat(),
            "is_approved": review.is_approved,
        }
        return JsonResponse(review_data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def approve_review(request, review_id):
    try:
        review = get_object_or_404(Review, id=review_id)
        review.is_approved = True
        review.save()
        return JsonResponse(
            {"success": True, "message": "Review approved successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_POST
def delete_review(request, review_id):
    try:
        review = get_object_or_404(Review, id=review_id)
        review.delete()
        return JsonResponse({"success": True, "message": "Review deleted successfully"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_POST
def resend_receipt(request, payment_id):
    try:
        ticket = get_object_or_404(Ticket, id=payment_id, status="SOLD")

        # Send receipt email
        subject = f"Payment Receipt - {ticket.tier.event.title}"
        html_message = render_to_string(
            "emails/payment_receipt.html", {"ticket": ticket}
        )
        plain_message = strip_tags(html_message)

        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [ticket.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        return JsonResponse(
            {"success": True, "message": "Payment receipt resent successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@staff_member_required
@require_GET
def get_user_details(request, user_id):
    try:
        user = get_object_or_404(User, id=user_id)
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "is_active": user.is_active,
        }
        return JsonResponse(user_data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@user_passes_test(is_admin)
def get_event_details(request, event_id):
    try:
        event = get_object_or_404(Event, id=event_id)
        data = {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'category': event.category,
            'date': event.date.isoformat(),
            'time': event.time.strftime('%H:%M'),
            'venue': event.venue.name if event.venue else event.custom_venue,
            'capacity': event.capacity,
            'status': event.status,
            'organizer': event.organizer.username,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@require_GET
def get_payment_details(request, payment_id):
    try:
        ticket = get_object_or_404(Ticket, id=payment_id)
        payment_data = {
            "id": ticket.id,
            "payment_id": ticket.payment_id,
            "tier": {
                "name": ticket.tier.name,
                "price": float(ticket.tier.price),
                "event": {"title": ticket.tier.event.title},
            },
            "user": {"username": ticket.user.username},
            "purchase_date": ticket.purchase_date.isoformat(),
            "status": ticket.status,
            "transaction_id": ticket.transaction_id,
        }
        return JsonResponse(payment_data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@user_passes_test(is_admin)
def update_event_status(request, event_id):
    if request.method == "POST":
        try:
            event = get_object_or_404(Event, id=event_id)
            data = json.loads(request.body)
            action = data.get("action")
            admin_notes = data.get("admin_notes", "")
            suggested_venue_ids = data.get("suggested_venues", [])

            if action not in ["APPROVED", "REJECTED"]:
                return JsonResponse({'error': 'Invalid action'}, status=400)

            if action == "APPROVED":
                event.status = "APPROVED"
                event.is_active = True
                event.admin_notes = admin_notes
                event.save()

                # Send approval email
                subject = f"Your Event '{event.title}' Has Been Approved"
                event_url = request.build_absolute_uri(
                    reverse('event_detail', args=[event.id])
                )
                
                context = {
                    'event': event,
                    'admin_notes': admin_notes,
                    'event_url': event_url,
                    'organizer': event.organizer,
                }
                
                html_message = render_to_string('emails/event_approved.html', context)
                plain_message = strip_tags(html_message)
                
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[event.organizer.email],
                    html_message=html_message,
                    fail_silently=False,
                )

                return JsonResponse({
                    'message': 'Event approved successfully',
                    'status': 'success'
                })
            else:  # REJECTED
                # Get suggested venues if any
                suggested_venues = []
                if suggested_venue_ids:
                    suggested_venues = Venue.objects.filter(
                        id__in=suggested_venue_ids,
                        is_available=True
                    ).values('id', 'name', 'capacity', 'address', 'description')

                # Send rejection email with venue suggestions
                subject = f"Your Event '{event.title}' Has Been Rejected"
                dashboard_url = request.build_absolute_uri(reverse('organizer_dashboard'))
                
                context = {
                    'event': event,
                    'admin_notes': admin_notes,
                    'suggested_venues': suggested_venues,
                    'organizer': event.organizer,
                    'dashboard_url': dashboard_url
                }
                
                html_message = render_to_string('emails/event_rejected.html', context)
                plain_message = strip_tags(html_message)
                
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[event.organizer.email],
                    html_message=html_message,
                    fail_silently=False,
                )

                # Delete the event after sending email
                event.delete()
                
                return JsonResponse({
                    'message': 'Event rejected successfully',
                    'status': 'success'
                })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
@user_passes_test(is_admin)
def get_available_venues(request):
    """Get available venues for a specific date"""
    try:
        date = request.GET.get('date')
        if not date:
            return JsonResponse({'error': 'Date is required'}, status=400)
            
        # Get all venues
        all_venues = Venue.objects.filter(is_available=True)
        
        # Get venues that are already booked for this date
        booked_venues = Event.objects.filter(
            date=date,
            status='APPROVED'
        ).values_list('venue_id', flat=True)
        
        # Filter out booked venues
        available_venues = all_venues.exclude(id__in=booked_venues)
        
        # Format venue data
        venues_data = [{
            'id': venue.id,
            'name': venue.name,
            'capacity': venue.capacity,
            'address': venue.address,
            'description': venue.description
        } for venue in available_venues]
        
        return JsonResponse({'venues': venues_data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
def check_venue_availability(request):
    """Check if a venue is available for a specific date"""
    try:
        venue_id = request.GET.get('venue_id')
        date = request.GET.get('date')
        
        if not venue_id or not date:
            return JsonResponse({'error': 'Venue ID and date are required'}, status=400)
            
        # Check if venue exists and is available
        venue = Venue.objects.filter(id=venue_id, is_available=True).first()
        if not venue:
            return JsonResponse({'available': False, 'message': 'Venue not found or not available'})
            
        # Check if venue is booked for the date
        is_booked = Event.objects.filter(
            venue_id=venue_id,
            date=date,
            status='APPROVED'
        ).exists()
        
        return JsonResponse({
            'available': not is_booked,
            'message': 'Venue is already booked for this date' if is_booked else 'Venue is available'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Admin Venue Views
@staff_member_required
def admin_venues_list(request):
    venues = Venue.objects.all()
    return render(request, 'admin_dashboard/venues.html', {'venues': venues})

@staff_member_required
@require_POST
def admin_add_venue(request):
    try:
        # Read data from request.POST instead of json.loads(request.body)
        name = request.POST.get('name')
        address = request.POST.get('address')
        capacity_str = request.POST.get('capacity')
        # Checkbox values are sent as 'on' if checked, and not sent if unchecked
        is_available = request.POST.get('is_available') == 'on'

        if not all([name, address, capacity_str]):
             return JsonResponse({"error": "Name, address, and capacity are required"}, status=400)

        try:
            capacity = int(capacity_str)
            if capacity < 0:
                 return JsonResponse({"error": "Capacity cannot be negative"}, status=400)
        except ValueError:
             return JsonResponse({"error": "Capacity must be a number"}, status=400)

        # Create the new venue
        venue = Venue.objects.create(
            name=name,
            address=address,
            capacity=capacity,
            is_available=is_available
        )

        return JsonResponse({'message': 'Venue added successfully', 'venue_id': venue.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
def admin_edit_venue(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id)

    if request.method == 'GET':
        # Return venue data as JSON for the edit modal
        venue_data = {
            'id': venue.id,
            'name': venue.name,
            'address': venue.address,
            'capacity': venue.capacity,
            'is_available': venue.is_available,
        }
        return JsonResponse(venue_data)

    elif request.method == 'POST':
        # Handle POST request to update the venue
        try:
            # Read data from request.POST instead of json.loads(request.body)
            venue.name = request.POST.get('name', venue.name)
            venue.address = request.POST.get('address', venue.address)
            capacity_str = request.POST.get('capacity', str(venue.capacity))
            # Handle checkbox value correctly (sent as 'on' or not sent)
            venue.is_available = request.POST.get('is_available') == 'on'

            try:
                venue.capacity = int(capacity_str)
                if venue.capacity < 0:
                    return JsonResponse({"error": "Capacity cannot be negative"}, status=400)
            except ValueError:
                return JsonResponse({"error": "Capacity must be a number"}, status=400)

            venue.save()

            return JsonResponse({'message': 'Venue updated successfully'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

@staff_member_required
@require_POST
def admin_delete_venue(request, venue_id):
    try:
        venue = get_object_or_404(Venue, id=venue_id)
        venue.delete()
        return JsonResponse({'message': 'Venue deleted successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Admin Ticket Tier Views
@staff_member_required
def admin_ticket_tiers_list(request):
    ticket_tiers = TicketTier.objects.all().select_related('event') # Select related event for display
    return render(request, 'admin_dashboard/ticket_tiers.html', {'ticket_tiers': ticket_tiers})

@staff_member_required
@require_POST
def admin_add_ticket_tier(request):
    try:
        # Read data from request.POST
        event_id = request.POST.get('event')
        name = request.POST.get('name')
        price_str = request.POST.get('price')
        # Use 'quantity' as the field name for total quantity, matching the model likely
        quantity_str = request.POST.get('quantity')

        if not all([event_id, name, price_str, quantity_str]):
             return JsonResponse({"error": "All fields are required"}, status=400)

        # Get the event
        event = get_object_or_404(Event, id=event_id)

        # Validate and convert price and quantity
        try:
            price = float(price_str)
            if price < 0:
                return JsonResponse({"error": "Price cannot be negative"}, status=400)
        except ValueError:
            return JsonResponse({"error": "Price must be a number"}, status=400)

        try:
            total_quantity = int(quantity_str) # Use total_quantity variable for clarity in logic
            if total_quantity < 0:
                 return JsonResponse({"error": "Total quantity cannot be negative"}, status=400)
        except ValueError:
             return JsonResponse({"error": "Total quantity must be an integer"}, status=400)

        # Create the new ticket tier
        # Use 'quantity' as the field name for the model
        tier = TicketTier.objects.create(
            event=event,
            name=name,
            price=price,
            quantity=total_quantity, # Assign to the 'quantity' field on the model
            # sold_quantity will likely default to 0
        )

        return JsonResponse({'message': 'Ticket tier added successfully', 'tier_id': tier.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
def admin_edit_ticket_tier(request, tier_id):
    tier = get_object_or_404(TicketTier, id=tier_id)

    if request.method == 'GET':
        # Return ticket tier data as JSON for the edit modal
        # Use 'total_quantity' key to match the frontend JavaScript expectation
        tier_data = {
            'id': tier.id,
            'event_id': tier.event.id,
            'event_title': tier.event.title, # Include event title for display
            'name': tier.name,
            'price': float(tier.price), # Convert Decimal to float for JSON serialization
            'total_quantity': tier.quantity, # Get total quantity from tier.quantity
            'available_tickets': tier.available_tickets,
        }
        return JsonResponse(tier_data)

    elif request.method == 'POST':
        # Handle POST request to update the ticket tier
        try:
            # Read data from request.POST
            tier.name = request.POST.get('name', tier.name)
            price_str = request.POST.get('price', str(tier.price))
            # Read total quantity from 'quantity' field in the form
            quantity_str = request.POST.get('quantity', str(tier.quantity))

            # Validate and convert price
            try:
                tier.price = float(price_str)
                if tier.price < 0:
                    return JsonResponse({"error": "Price cannot be negative"}, status=400)
            except ValueError:
                return JsonResponse({"error": "Price must be a number"}, status=400)

            # Validate and update total quantity
            try:
                new_total_quantity = int(quantity_str) # Use total_quantity variable for clarity in logic
                if new_total_quantity < 0:
                     return JsonResponse({"error": "Total quantity cannot be negative"}, status=400)

                # Prevent setting total quantity below tickets already sold
                # Calculate sold tickets based on the tier's sold_quantity field
                sold_tickets = tier.sold_quantity

                if new_total_quantity < sold_tickets:
                     return JsonResponse({"error": f"Total quantity cannot be less than {sold_tickets} tickets already sold"}, status=400)

                # Update the total quantity. The model should manage available_tickets.
                tier.quantity = new_total_quantity # Assign to the 'quantity' field on the model
                # tier.available_tickets is likely managed by the model, do not assign directly here

            except ValueError:
                 return JsonResponse({"error": "Total quantity must be an integer"}, status=400)

            tier.save()

            return JsonResponse({'message': 'Ticket tier updated successfully'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

@staff_member_required
@require_POST
def admin_delete_ticket_tier(request, tier_id):
    try:
        tier = get_object_or_404(TicketTier, id=tier_id)
        # Before deleting the tier, consider if there are associated tickets.
        # Depending on business logic, you might prevent deletion, mark tickets as invalid, etc.
        # For now, we'll just delete the tier.
        tier.delete()
        return JsonResponse({'message': 'Ticket tier deleted successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@staff_member_required
@require_GET
def admin_get_events_json(request):
    """Returns a list of events as JSON for use in dropdowns, etc."""
    try:
        events = Event.objects.all().values('id', 'title').order_by('title')
        return JsonResponse({'events': list(events)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@user_passes_test(is_admin)
def admin_add_event(request):
    if request.method == 'POST':
        form = EventAdminForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.status = 'APPROVED'
            event.save()
            messages.success(request, 'Event added successfully!')
            return redirect('admin_events')  # Redirect to event list instead
    else:
        form = EventAdminForm()
    
    venues = Venue.objects.filter(is_available=True)
    context = {
        'form': form,
        'venues': venues,
        'title': 'Add New Event'
    }
    return render(request, 'admin_dashboard/event_form.html', context)

@user_passes_test(is_admin)
def admin_edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    if request.method == 'POST':
        form = EventAdminForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully!')
            return redirect('admin_events')  # Redirect to event list instead
    else:
        form = EventAdminForm(instance=event)
    
    venues = Venue.objects.filter(is_available=True)
    context = {
        'form': form,
        'venues': venues,
        'title': 'Edit Event',
        'event': event
    }
    return render(request, 'admin_dashboard/event_form_edit.html', context)
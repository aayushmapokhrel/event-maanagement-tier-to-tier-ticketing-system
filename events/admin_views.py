from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Sum, F
from django.utils import timezone
from datetime import timedelta
from .models import Event, Ticket, Review
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
import json
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import os


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


@staff_member_required
def admin_events(request):
    # Get all events with optimized query
    events = (
        Event.objects.select_related("organizer")
        .prefetch_related("ticket_tiers__tickets")
        .all()
    )

    # Add today's date to context for status comparison
    context = {"events": events, "today": timezone.now().date()}
    return render(request, "admin_dashboard/events.html", context)


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


@staff_member_required
@require_POST
def add_event(request):
    try:
        # Get form data
        title = request.POST.get("name")
        category = request.POST.get("category")
        venue = request.POST.get("venue")
        capacity = request.POST.get("capacity")
        description = request.POST.get("description")
        image = request.FILES.get("image")

        # Handle date and time separately
        date_str = request.POST.get("date")
        time_str = request.POST.get("time")
        if not date_str or not time_str:
            return JsonResponse({"error": "Date and time are required"}, status=400)

        from datetime import datetime

        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        event_time = datetime.strptime(time_str, "%H:%M").time()

        # Create event
        event = Event.objects.create(
            title=title,
            category=category,
            date=event_date,
            time=event_time,
            venue=venue,
            capacity=capacity,
            description=description,
            organizer=request.user,
        )

        if image:
            event.image = image
            event.save()

        return JsonResponse(
            {"message": "Event created successfully", "event_id": event.id}
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def update_event(request, event_id):
    try:
        event = get_object_or_404(Event, id=event_id)

        # Get form data
        event.title = request.POST.get("name", event.title)
        event.category = request.POST.get("category", event.category)
        event.venue = request.POST.get("venue", event.venue)
        event.capacity = request.POST.get("capacity", event.capacity)
        event.description = request.POST.get("description", event.description)

        # Handle date and time separately
        date_str = request.POST.get("date")
        time_str = request.POST.get("time")
        if date_str and time_str:
            from datetime import datetime

            event.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            event.time = datetime.strptime(time_str, "%H:%M").time()

        # Handle image upload
        if "image" in request.FILES:
            event.image = request.FILES["image"]

        event.save()
        return JsonResponse({"message": "Event updated successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@staff_member_required
@require_POST
def delete_event(request, event_id):
    try:
        event = get_object_or_404(Event, id=event_id)
        event.delete()
        return JsonResponse({"message": "Event deleted successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


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


@staff_member_required
@require_GET
def get_event_details(request, event_id):
    try:
        event = get_object_or_404(Event, id=event_id)
        event_data = {
            "id": event.id,
            "title": event.title,
            "date": event.date.strftime("%Y-%m-%d"),
            "venue": event.venue,
            "description": event.description,
            "category": event.category,
            "capacity": event.capacity,
            "image_url": event.image.url if event.image else None,
        }
        return JsonResponse(event_data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


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

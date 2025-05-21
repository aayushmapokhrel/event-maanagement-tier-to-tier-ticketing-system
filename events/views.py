from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout as auth_logout
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import Event, TicketTier, Ticket, Review, UserProfile
from .forms import UserRegistrationForm, UserProfileForm, EventForm, TicketTierForm, ReviewForm
import json

from .utils.khalti import KhaltiPayment
import requests
from django.db.models import F, Count, Sum, Avg
from django.db.models.functions import TruncDate, TruncMonth
import csv
import xlsxwriter
from django.utils import timezone
from datetime import datetime, timedelta
from django.utils.timesince import timesince

def home(request):
    featured_events = Event.objects.filter(is_active=True).order_by('-created_at')[:6]
    return render(request, 'events/home.html', {'featured_events': featured_events})

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('home')
    else:
        form = UserRegistrationForm()
    return render(request, 'events/register.html', {'form': form})

@login_required
def profile(request):
    # Get or create UserProfile
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'events/profile.html', {'form': form})
def event_list(request):
    # Start with ordered queryset
    events = Event.objects.filter(is_active=True).order_by('-date', '-time', 'title')
    
    # Search functionality
    query = request.GET.get('q')
    if query:
        events = events.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__icontains=query)
        )
    
    # Category filter
    category = request.GET.get('category')
    if category:
        events = events.filter(category=category)
    
    # Pagination
    paginator = Paginator(events, 12)
    page = request.GET.get('page')
    events = paginator.get_page(page)
    
    return render(request, 'events/event_list.html', {'events': events})

def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    ticket_tiers = event.ticket_tiers.all()
    reviews = event.reviews.all().order_by('-created_at')
    
    if request.method == 'POST' and request.user.is_authenticated:
        review_form = ReviewForm(request.POST)
        if review_form.is_valid():
            review = review_form.save(commit=False)
            review.event = event
            review.user = request.user
            review.save()
            messages.success(request, 'Review submitted successfully!')
            return redirect('event_detail', event_id=event.id)
    else:
        review_form = ReviewForm()
    
    context = {
        'event': event,
        'ticket_tiers': ticket_tiers,
        'reviews': reviews,
        'review_form': review_form,
    }
    return render(request, 'events/event_detail.html', context)

@login_required
def create_event(request):
    if request.method == 'POST':
        event_form = EventForm(request.POST, request.FILES)
        if event_form.is_valid():
            event = event_form.save(commit=False)
            event.organizer = request.user
            event.save()
            messages.success(request, 'Event created successfully!')
            return redirect('event_detail', event_id=event.id)
    else:
        event_form = EventForm()
    
    return render(request, 'events/create_event.html', {'form': event_form})

@login_required
def edit_event(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, 'Event updated successfully!')
            return redirect('event_detail', event_id=event.id)
    else:
        form = EventForm(instance=event)
    
    return render(request, 'events/edit_event.html', {'form': form, 'event': event})

@login_required
def create_ticket_tier(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    
    if request.method == 'POST':
        form = TicketTierForm(request.POST)
        if form.is_valid():
            ticket_tier = form.save(commit=False)
            ticket_tier.event = event
            ticket_tier.save()
            messages.success(request, 'Ticket tier created successfully!')
            return redirect('event_detail', event_id=event.id)
    else:
        form = TicketTierForm()
    
    return render(request, 'events/create_ticket_tier.html', {'form': form, 'event': event})


@login_required
def purchase_ticket(request, tier_id):
    ticket_tier = get_object_or_404(TicketTier, id=tier_id)
    
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        
        # Validate quantity
        if quantity <= 0 or quantity > ticket_tier.available_tickets:
            messages.error(request, 'Invalid quantity selected.')
            return redirect('event_detail', event_id=ticket_tier.event.id)
        
        try:
            # Create ticket (initially with PENDING status)
            ticket = Ticket.objects.create(
                tier=ticket_tier,
                user=request.user,
                status='PENDING',
                quantity=quantity
            )
            
            # Initiate Khalti payment
            payment_data = KhaltiPayment.initiate_payment(
                request,
                ticket,
                'verify_payment'
            )
            
            # Update ticket with payment ID
            ticket.payment_id = payment_data.get('pidx', '')
            ticket.save()
            
            # Redirect to Khalti payment page
            return redirect(payment_data['payment_url'])
            
        except Exception as e:
            # Clean up ticket if payment initiation fails
            if 'ticket' in locals():
                ticket.delete()
            messages.error(request, str(e))
            return redirect('event_detail', event_id=ticket_tier.event.id)
    
    return render(request, 'events/purchase_ticket.html', {
        'ticket_tier': ticket_tier,
        'khalti_public_key': settings.KHALTI_PUBLIC_KEY
    })

@login_required
def verify_payment(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user)
    pidx = request.GET.get('pidx') or ticket.payment_id
    
    if not pidx:
        messages.error(request, 'Invalid payment verification request.')
        return redirect('event_detail', event_id=ticket.tier.event.id)
    
    try:
        # Verify payment with Khalti
        verification = KhaltiPayment.verify_payment(pidx)
        
        if verification.get('status') == 'Completed':
            # Check ticket availability again (in case sold out during payment)
            if not ticket.tier.decrease_available_tickets(ticket.quantity):
                messages.error(request, 'Sorry, not enough tickets available now.')
                ticket.status = 'CANCELLED'
                ticket.save()
                return redirect('event_detail', event_id=ticket.tier.event.id)
            
            # Update ticket status to SOLD (this will generate QR code)
            ticket.status = 'SOLD'
            ticket.payment_id = pidx
            ticket.save()
            
            # Send confirmation email
            send_ticket_confirmation_email(request, ticket)
            
            messages.success(request, 'Payment successful! Your ticket has been confirmed.')
            return redirect('my_tickets')
        else:
            ticket.status = 'CANCELLED'
            ticket.save()
            messages.error(request, f'Payment verification failed. Status: {verification.get("status")}')
    
    except Exception as e:
        messages.error(request, str(e))
    
    return redirect('event_detail', event_id=ticket.tier.event.id)

# views.py
from django.urls import reverse
from django.utils.dateformat import format

def send_ticket_confirmation_email(request, ticket):
    """Send ticket confirmation email with all details"""
    subject = f'Ticket Confirmation - {ticket.tier.event.title}'
    
    # Format dates and times properly
    event_date = ticket.tier.event.date.strftime('%B %d, %Y')  # e.g. "January 01, 2023"
    event_time = ticket.tier.event.time.strftime('%I:%M %p')   # e.g. "02:30 PM"
    
    context = {
        'user': request.user,
        'event': {
            'title': ticket.tier.event.title,
            'date': event_date,
            'time': event_time,
            'venue': ticket.tier.event.venue,
        },
        'tier_name': ticket.tier.name,
        'quantity': ticket.quantity,
        'total_price': ticket.get_total_price(),
        'my_tickets_url': request.build_absolute_uri(reverse('my_tickets'))
    }
    
    html_message = render_to_string('emails/ticket_confirmation.html', context)
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            html_message=html_message
        )
    except Exception as e:
        logger.error(f"Failed to send ticket confirmation email: {str(e)}")


@login_required
def my_tickets(request):
    tickets = Ticket.objects.filter(user=request.user).order_by('-purchase_date')
    return render(request, 'events/my_tickets.html', {'tickets': tickets})

@login_required
def download_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user)
    return render(request, 'events/download_ticket.html', {'ticket': ticket})

@login_required
def verify_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    # Only event organizers can verify tickets
    if request.user != ticket.tier.event.organizer:
        messages.error(request, 'You do not have permission to verify tickets for this event.')
        return redirect('event_detail', event_id=ticket.tier.event.id)
    
    # Check if ticket is valid
    if ticket.status != 'SOLD':
        messages.error(request, 'This ticket is not valid for entry.')
        return render(request, 'events/verify_ticket.html', {
            'ticket': ticket,
            'is_valid': False,
            'reason': f'Ticket status is {ticket.status}'
        })
    
    # Check if ticket has already been used
    if ticket.status == 'USED':
        messages.error(request, 'This ticket has already been used.')
        return render(request, 'events/verify_ticket.html', {
            'ticket': ticket,
            'is_valid': False,
            'reason': 'Ticket has already been used'
        })
    
    # Check if event date is valid
    if ticket.tier.event.is_past_event:
        messages.error(request, 'This event has already passed.')
        return render(request, 'events/verify_ticket.html', {
            'ticket': ticket,
            'is_valid': False,
            'reason': 'Event has already passed'
        })
    
    if request.method == 'POST':
        # Mark ticket as used and record check-in time
        if ticket.check_in():
            messages.success(request, 'Ticket successfully verified and marked as used.')
            return redirect('checkin_dashboard', event_id=ticket.tier.event.id)
        else:
            messages.error(request, 'Failed to check in ticket. Please try again.')
    
    return render(request, 'events/verify_ticket.html', {
        'ticket': ticket,
        'is_valid': True
    })

@login_required
def scan_ticket(request):
    """View for scanning QR codes"""
    return render(request, 'events/scan_ticket.html')

@login_required
def manage_attendees(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    tickets = Ticket.objects.filter(tier__event=event).select_related('user', 'tier')
    
    # Get check-in statistics
    stats = {
        'total': tickets.count(),
        'checked_in': tickets.filter(status='USED').count(),
        'pending': tickets.filter(status='SOLD').count(),
    }
    
    # Handle export requests
    if 'export' in request.GET:
        export_format = request.GET.get('export')
        if export_format == 'csv':
            return export_attendees_csv(tickets, event)
        elif export_format == 'excel':
            return export_attendees_excel(tickets, event)
    
    return render(request, 'events/manage_attendees.html', {
        'event': event,
        'tickets': tickets,
        'stats': stats,
    })

def export_attendees_csv(tickets, event):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{event.title}_attendees_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Ticket ID', 'Attendee Name', 'Email', 'Ticket Type', 'Purchase Date', 'Check-in Status'])
    
    for ticket in tickets:
        writer.writerow([
            ticket.id,
            ticket.user.get_full_name() or ticket.user.username,
            ticket.user.email,
            ticket.tier.name,
            ticket.purchase_date.strftime('%Y-%m-%d %H:%M:%S'),
            ticket.status
        ])
    
    return response

def export_attendees_excel(tickets, event):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{event.title}_attendees_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    
    workbook = xlsxwriter.Workbook(response, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    
    # Add header row
    headers = ['Ticket ID', 'Attendee Name', 'Email', 'Ticket Type', 'Purchase Date', 'Check-in Status']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)
    
    # Add data rows
    for row, ticket in enumerate(tickets, start=1):
        worksheet.write(row, 0, ticket.id)
        worksheet.write(row, 1, ticket.user.get_full_name() or ticket.user.username)
        worksheet.write(row, 2, ticket.user.email)
        worksheet.write(row, 3, ticket.tier.name)
        worksheet.write(row, 4, ticket.purchase_date.strftime('%Y-%m-%d %H:%M:%S'))
        worksheet.write(row, 5, ticket.status)
    
    workbook.close()
    return response

@login_required
def checkin_dashboard(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    
    # Get real-time check-in statistics
    tickets = Ticket.objects.filter(tier__event=event)
    stats = {
        'total_tickets': tickets.count(),
        'checked_in': tickets.filter(status='USED').count(),
        'pending': tickets.filter(status='SOLD').count(),
        'by_tier': tickets.values('tier__name').annotate(
            total=Count('id'),
            checked_in=Count('id', filter=Q(status='USED'))
        )
    }
    
    # Get recent check-ins
    recent_checkins = tickets.filter(status='USED').order_by('-updated_at')[:10]
    
    return render(request, 'events/checkin_dashboard.html', {
        'event': event,
        'stats': stats,
        'recent_checkins': recent_checkins,
    })

@login_required
def checkin_stats(request, event_id):
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    tickets = Ticket.objects.filter(tier__event=event)
    
    # Get real-time statistics
    stats = {
        'total_tickets': tickets.count(),
        'checked_in': tickets.filter(status='USED').count(),
        'pending': tickets.filter(status='SOLD').count(),
    }
    
    # Get recent check-ins
    recent_checkins = tickets.filter(status='USED').order_by('-check_in_time')[:10]
    recent_checkins_data = [{
        'user_name': checkin.user.get_full_name() or checkin.user.username,
        'tier_name': checkin.tier.name,
        'time_ago': timesince(checkin.check_in_time)
    } for checkin in recent_checkins]
    
    # Add recent check-ins to response
    stats['recent_checkins'] = recent_checkins_data
    
    return JsonResponse(stats)

@login_required
def organizer_dashboard(request):
    """Dashboard for event organizers with analytics and management tools"""
    
    # Get all events organized by the user
    events = Event.objects.filter(organizer=request.user)
    
    # Get overall statistics
    total_events = events.count()
    active_events = events.filter(is_active=True).count()
    
    # Get total tickets sold (considering quantity)
    total_tickets = Ticket.objects.filter(
        tier__event__organizer=request.user,
        status='SOLD'
    ).aggregate(
        total=Sum('quantity')
    )['total'] or 0
    
    # Calculate total revenue (price * quantity)
    total_revenue = Ticket.objects.filter(
        tier__event__organizer=request.user,
        status='SOLD'
    ).aggregate(
        total=Sum(F('tier__price') * F('quantity'))
    )['total'] or 0
    
    # Get ticket sales by event
    event_sales = events.annotate(
        tickets_sold=Sum('ticket_tiers__tickets__quantity', filter=Q(ticket_tiers__tickets__status='SOLD')),
        revenue=Sum(F('ticket_tiers__tickets__tier__price') * F('ticket_tiers__tickets__quantity'), 
                   filter=Q(ticket_tiers__tickets__status='SOLD'))
    )
    
    # Get daily sales for the last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_sales = Ticket.objects.filter(
        tier__event__organizer=request.user,
        status='SOLD',
        purchase_date__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('purchase_date')
    ).values('date').annotate(
        count=Sum('quantity'),
        revenue=Sum(F('tier__price') * F('quantity'))
    ).order_by('date')
    
    # Get monthly revenue
    monthly_revenue = Ticket.objects.filter(
        tier__event__organizer=request.user,
        status='SOLD'
    ).annotate(
        month=TruncMonth('purchase_date')
    ).values('month').annotate(
        revenue=Sum(F('tier__price') * F('quantity'))
    ).order_by('month')
    
    # Get ticket type distribution
    ticket_types = TicketTier.objects.filter(
        event__organizer=request.user
    ).values('name').annotate(
        count=Sum('tickets__quantity', filter=Q(tickets__status='SOLD')),
        revenue=Sum(F('tickets__tier__price') * F('tickets__quantity'), 
                   filter=Q(tickets__status='SOLD'))
    )
    
    # Get recent transactions
    recent_transactions = Ticket.objects.filter(
        tier__event__organizer=request.user,
        status='SOLD'
    ).select_related('user', 'tier', 'tier__event').order_by('-purchase_date')[:10]
    
    # Get upcoming events
    upcoming_events = events.filter(
        date__gte=timezone.now().date(),
        is_active=True
    ).order_by('date')[:5]
    
    context = {
        'total_events': total_events,
        'active_events': active_events,
        'total_tickets': total_tickets,
        'total_revenue': total_revenue,
        'event_sales': event_sales,
        'daily_sales': daily_sales,
        'monthly_revenue': monthly_revenue,
        'ticket_types': ticket_types,
        'recent_transactions': recent_transactions,
        'upcoming_events': upcoming_events,
    }
    
    return render(request, 'events/organizer_dashboard.html', context)

@login_required
def event_analytics(request, event_id):
    """Detailed analytics for a specific event"""
    
    event = get_object_or_404(Event, id=event_id, organizer=request.user)
    
    # Get ticket sales statistics
    ticket_stats = Ticket.objects.filter(tier__event=event).aggregate(
        total_sold=Count('id', filter=Q(status='SOLD')),
        total_revenue=Sum('tier__price', filter=Q(status='SOLD')),
        avg_price=Avg('tier__price', filter=Q(status='SOLD'))
    )
    
    # Get sales by ticket tier
    tier_sales = TicketTier.objects.filter(event=event).annotate(
        sold=Count('tickets', filter=Q(tickets__status='SOLD')),
        revenue=Sum('tickets__tier__price', filter=Q(tickets__status='SOLD'))
    )
    
    # Get daily sales for this event
    daily_sales = Ticket.objects.filter(
        tier__event=event,
        status='SOLD'
    ).annotate(
        date=TruncDate('purchase_date')
    ).values('date').annotate(
        count=Count('id'),
        revenue=Sum('tier__price')
    ).order_by('date')
    
    # Get check-in statistics
    checkin_stats = Ticket.objects.filter(tier__event=event).aggregate(
        total_checked=Count('id', filter=Q(status='USED')),
        pending_checkin=Count('id', filter=Q(status='SOLD'))
    )
    
    context = {
        'event': event,
        'ticket_stats': ticket_stats,
        'tier_sales': tier_sales,
        'daily_sales': daily_sales,
        'checkin_stats': checkin_stats,
    }
    
    return render(request, 'events/event_analytics.html', context)

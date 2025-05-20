from django.urls import path
from . import views, admin_views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Core pages
    path('', views.home, name='home'),
    path('events/', views.event_list, name='event_list'),
    
    # User management
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    
    # Event management
    path('events/create/', views.create_event, name='create_event'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/edit/', views.edit_event, name='edit_event'),
    path('events/<int:event_id>/create-tier/', views.create_ticket_tier, name='create_ticket_tier'),
    
    # Ticket management
    path('tickets/purchase/<int:tier_id>/', views.purchase_ticket, name='purchase_ticket'),
    path('payment/verify/<int:ticket_id>/', views.verify_payment, name='verify_payment'),
    path('my-tickets/', views.my_tickets, name='my_tickets'),
    path('tickets/download/<int:ticket_id>/', views.download_ticket, name='download_ticket'),
    path('tickets/verify/<int:ticket_id>/', views.verify_ticket, name='verify_ticket'),
    path('tickets/scan/', views.scan_ticket, name='scan_ticket'),
    
    # Organizer tools
    path('events/<int:event_id>/manage-attendees/', views.manage_attendees, name='manage_attendees'),
    path('events/<int:event_id>/checkin-dashboard/', views.checkin_dashboard, name='checkin_dashboard'),
    path('events/<int:event_id>/checkin-stats/', views.checkin_stats, name='checkin_stats'),
    path('events/<int:event_id>/analytics/', views.event_analytics, name='event_analytics'),
    path('organizer/dashboard/', views.organizer_dashboard, name='organizer_dashboard'),

    # Admin Dashboard URLs
    path('custom-admin/dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('custom-admin/users/', admin_views.admin_users, name='admin_users'),
    path('custom-admin/users/<int:user_id>/', admin_views.get_user_details, name='admin_get_user'),
    path('custom-admin/users/add/', admin_views.add_user, name='admin_add_user'),
    path('custom-admin/users/<int:user_id>/update/', admin_views.update_user, name='admin_update_user'),
    path('custom-admin/users/<int:user_id>/toggle/', admin_views.toggle_user_status, name='admin_toggle_user'),
    path('custom-admin/users/<int:user_id>/delete/', admin_views.delete_user, name='admin_delete_user'),
    
    path('custom-admin/events/', admin_views.admin_events, name='admin_events'),
    path('custom-admin/events/<int:event_id>/', admin_views.get_event_details, name='admin_get_event'),
    path('custom-admin/events/add/', admin_views.add_event, name='admin_add_event'),
    path('custom-admin/events/<int:event_id>/update/', admin_views.update_event, name='admin_update_event'),
    path('custom-admin/events/<int:event_id>/delete/', admin_views.delete_event, name='admin_delete_event'),
    path('custom-admin/events/<int:event_id>/tickets/', admin_views.event_tickets, name='admin_event_tickets'),
    
    path('custom-admin/tickets/', admin_views.admin_tickets, name='admin_tickets'),
    path('custom-admin/tickets/<int:ticket_id>/', admin_views.get_ticket_details, name='get_ticket_details'),
    path('custom-admin/tickets/<int:ticket_id>/resend/', admin_views.resend_ticket, name='resend_ticket'),
    path('custom-admin/tickets/<int:ticket_id>/cancel/', admin_views.cancel_ticket, name='cancel_ticket'),
    path('custom-admin/reviews/', admin_views.admin_reviews, name='admin_reviews'),
    path('custom-admin/reviews/<int:review_id>/approve/', admin_views.approve_review, name='admin_approve_review'),
    path('custom-admin/reviews/<int:review_id>/delete/', admin_views.delete_review, name='admin_delete_review'),
    path('custom-admin/reviews/<int:review_id>/', admin_views.get_review_details, name='get_review_details'),
    path('custom-admin/payments/', admin_views.admin_payments, name='admin_payments'),
    path('custom-admin/payments/<int:payment_id>/', admin_views.get_payment_details, name='get_payment_details'),
    path('custom-admin/payments/<int:payment_id>/resend-receipt/', admin_views.resend_receipt, name='admin_resend_receipt'),
    path('custom-admin/settings/', admin_views.admin_settings, name='admin_settings'),
    path('custom-admin/settings/update/emailSettingsForm/', admin_views.update_email_settings, name='update_email_settings'),
    path('custom-admin/settings/update/paymentSettingsForm/', admin_views.update_payment_settings, name='update_payment_settings'),
    path('custom-admin/settings/update/generalSettingsForm/', admin_views.update_general_settings, name='update_general_settings'),
    path('custom-admin/settings/update/notificationSettingsForm/', admin_views.update_notification_settings, name='update_notification_settings'),
    
    # Custom Admin Authentication
    path('custom-admin/logout/', auth_views.LogoutView.as_view(next_page='admin_dashboard'), name='admin_logout'),
]
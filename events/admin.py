from django.contrib import admin
from .models import UserProfile, Event, TicketTier, Ticket, Review, Venue
from django.utils.html import format_html


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "capacity")
    search_fields = ("name", "address")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "address")
    search_fields = ("user__username", "phone_number")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'organizer', 'date', 'time', 'category', 'status', 'is_active')
    list_filter = ('status', 'category', 'is_active')
    search_fields = ('title', 'description', 'organizer__username')
    readonly_fields = ('created_at', 'total_tickets_sold')
    fieldsets = (
        ('Event Information', {
            'fields': ('title', 'description', 'category', 'image')
        }),
        ('Event Details', {
            'fields': ('date', 'time', 'venue', 'custom_venue', 'capacity')
        }),
        ('Status Information', {
            'fields': ('status', 'admin_notes', 'is_active')
        }),
        ('System Information', {
            'fields': ('organizer', 'created_at', 'total_tickets_sold')
        }),
    )


@admin.register(TicketTier)
class TicketTierAdmin(admin.ModelAdmin):
    list_display = ("event", "name", "price", "quantity", "available_tickets")
    list_filter = ("name", "event")
    search_fields = ("event__title",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'tier', 'quantity', 'status', 'purchase_date')
    list_filter = ('status', 'purchase_date')
    search_fields = ('user__username', 'tier__event__title')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'rating', 'created_at', 'is_approved')
    list_filter = ('rating', 'is_approved', 'created_at')
    search_fields = ('user__username', 'event__title', 'comment')

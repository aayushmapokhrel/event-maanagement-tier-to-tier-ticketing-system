from django.contrib import admin
from .models import UserProfile, Event, TicketTier, Ticket, Review


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "address")
    search_fields = ("user__username", "phone_number")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "organizer", "category", "date", "time", "is_active")
    list_filter = ("category", "is_active", "date")
    search_fields = ("title", "description", "organizer__username")
    date_hierarchy = "date"


@admin.register(TicketTier)
class TicketTierAdmin(admin.ModelAdmin):
    list_display = ("event", "name", "price", "quantity", "available_tickets")
    list_filter = ("name", "event")
    search_fields = ("event__title",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("tier", "user", "purchase_date", "status","payment_method")
    list_filter = ("status", "purchase_date","payment_method")
    search_fields = ("user__username", "tier__event__title")
    date_hierarchy = "purchase_date"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("event__title", "user__username", "comment")

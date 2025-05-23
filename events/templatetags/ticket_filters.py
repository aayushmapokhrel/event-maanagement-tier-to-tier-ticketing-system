# events/templatetags/ticket_filters.py
from django import template
from django.utils import timezone
from datetime import datetime

register = template.Library()

@register.filter
def filter_tickets(tickets, statuses):
    status_list = [s.strip() for s in statuses.split(',')]
    return [t for t in tickets if t.status in status_list]

@register.filter
def filter_past_events(tickets):
    today = timezone.now().date()
    return [t for t in tickets if t.tier.event.date < today]
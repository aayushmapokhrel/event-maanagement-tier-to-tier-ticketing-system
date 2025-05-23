from django import template

register = template.Library()


@register.filter
def sub(value, arg):
    """Subtract the arg from the value."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value


@register.filter
def sum_ticket_prices(tickets):
    """Sum the prices of all tickets using their tiers."""
    try:
        return sum(ticket.tier.price for ticket in tickets)
    except (ValueError, TypeError, AttributeError):
        return 0

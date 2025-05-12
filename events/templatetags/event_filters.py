from django import template

register = template.Library()

@register.filter(name='split')
def split(value, delimiter=','):
    """Split a string into a list using the specified delimiter."""
    return value.split(delimiter) 
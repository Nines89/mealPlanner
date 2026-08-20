from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up a dict key from a template variable (e.g. {{ d|get_item:variable }})."""
    if dictionary is None:
        return None
    return dictionary.get(key)

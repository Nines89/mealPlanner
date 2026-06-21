from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Accesso a dict per chiave dinamica nei template (es. {{ d|get_item:variabile }})."""
    if dictionary is None:
        return None
    return dictionary.get(key)

from django import template

register = template.Library()

_GENRE_EMOJI = {
    'pasta_cereali': '🍝',
    'pollo_tacchino': '🍗',
    'pesce': '🐟',
    'carni_rosse': '🥩',
    'insaccati': '🥓',
    'uova': '🥚',
    'legumi': '🫘',
    'verdura': '🥦',
    'formaggio': '🧀',
    'zuppe': '🍲',
    'insalate': '🥗',
    'piadine': '🫓',
}


@register.filter
def get_item(dictionary, key):
    """Look up a dict key from a template variable (e.g. {{ d|get_item:variable }})."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def genre_emoji(genre):
    """Palette emoji for a recipe category value."""
    return _GENRE_EMOJI.get(genre, '🍽️')


@register.filter
def pct_of(part, whole):
    """Integer percent of whole, or 0 if whole is missing/zero."""
    try:
        whole_value = float(whole)
        if whole_value <= 0:
            return 0
        return int(round(float(part) / whole_value * 100))
    except (TypeError, ValueError):
        return 0


@register.filter
def at_most(value, cap):
    """Clamp a number so progress bars do not overflow."""
    try:
        return min(int(value), int(cap))
    except (TypeError, ValueError):
        return 0

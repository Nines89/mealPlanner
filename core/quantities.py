"""Human-readable ingredient quantities; nutrition remains stored in grams."""
from decimal import Decimal, ROUND_CEILING


EGG_GRAMS_PER_PIECE = Decimal('50')
MAX_WHOLE_EGGS_PER_PERSON_PER_MEAL = 3
MAX_WHOLE_EGG_GRAMS_PER_PERSON_PER_MEAL = (
    EGG_GRAMS_PER_PIECE * MAX_WHOLE_EGGS_PER_PERSON_PER_MEAL
)
_WHOLE_EGG_NAMES = {'uova', 'uovo', 'uova intere'}


def is_whole_egg(ingredient):
    return ingredient.name.strip().casefold() in _WHOLE_EGG_NAMES


def format_ingredient_quantity(ingredient, grams, *, whole_pieces=False):
    """Format whole eggs as a count and all other ingredients as grams."""
    grams = Decimal(grams)
    if is_whole_egg(ingredient):
        count = grams / EGG_GRAMS_PER_PIECE
        if whole_pieces:
            count = count.to_integral_value(rounding=ROUND_CEILING)
        count_text = _format_decimal(count)
        unit = 'uovo' if count == 1 else 'uova'
        return f'{count_text} {unit}'
    if grams < Decimal('1000'):
        return f'{grams:.0f} g'
    kilograms = (grams / Decimal('1000')).normalize()
    return f'{str(kilograms).replace(".", ",")} kg'


def _format_decimal(value):
    normalized = value.normalize()
    return str(normalized).replace('.', ',')

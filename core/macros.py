"""Shared macro dict helpers. Values are Decimal-compatible numbers."""
from decimal import Decimal

MACRO_NAMES = ('kcal', 'protein', 'carbs', 'fat')
ZERO = Decimal('0')
GRAMS_PER_100 = Decimal('100')


def empty_macros():
    return {name: ZERO for name in MACRO_NAMES}


def sum_macros(left, right):
    return {name: left[name] + right[name] for name in MACRO_NAMES}


def scale_macros(macros, factor):
    return {name: macros[name] * factor for name in MACRO_NAMES}


def macros_for_grams(ingredient, grams):
    ratio = Decimal(grams) / GRAMS_PER_100
    return {
        'kcal': Decimal(ingredient.kcal) * ratio,
        'protein': Decimal(ingredient.protein) * ratio,
        'carbs': Decimal(ingredient.carbs) * ratio,
        'fat': Decimal(ingredient.fat) * ratio,
    }

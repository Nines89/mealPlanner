"""
Week-plan nutrition totals for a shared household plate.

Expected: ON/OFF target for that weekday × household size.
Effective: macros of each assigned meal's grams × household size.
"""
from decimal import Decimal

from .macros import GRAMS_PER_100, empty_macros, scale_macros, sum_macros
from .models import MealGenre

_DAYS = range(7)


def plate_macros_for_meal(meal):
    """Macros of one shared plate (MealIngredient.grams as stored)."""
    if meal is None:
        return empty_macros()
    total = empty_macros()
    for meal_ingredient in meal.meal_ingredients.select_related('ingredient').all():
        total = sum_macros(total, _macros_for_meal_ingredient(meal_ingredient))
    return total


def _macros_for_meal_ingredient(meal_ingredient):
    ingredient = meal_ingredient.ingredient
    ratio = Decimal(meal_ingredient.grams) / GRAMS_PER_100
    return {
        'kcal': ingredient.kcal * ratio,
        'protein': ingredient.protein * ratio,
        'carbs': ingredient.carbs * ratio,
        'fat': ingredient.fat * ratio,
        'name': ingredient.name,
        'grams': meal_ingredient.grams,
    }


def meal_breakdown(meal):
    """Plate macros plus per-ingredient grams and macros."""
    if meal is None:
        return {'macros': empty_macros(), 'items': []}
    items = []
    total = empty_macros()
    queryset = meal.meal_ingredients.select_related('ingredient').order_by('id')
    for meal_ingredient in queryset:
        item = _macros_for_meal_ingredient(meal_ingredient)
        items.append(item)
        total = sum_macros(total, item)
    return {'macros': total, 'items': items}


def expected_macros_for_day(nutrition_target, member_count):
    """Household expected macros for one day, or None if no target."""
    if nutrition_target is None:
        return None
    multiplier = Decimal(member_count or 1)
    return {
        'kcal': Decimal(nutrition_target.target_kcal) * multiplier,
        'protein': Decimal(nutrition_target.target_protein) * multiplier,
        'carbs': Decimal(nutrition_target.target_carbs) * multiplier,
        'fat': Decimal(nutrition_target.target_fat) * multiplier,
    }


def compute_week_totals(targets_by_day, slots_with_meal, member_count):
    """
    Household expected vs effective totals.

    ``targets_by_day`` is {day: NutritionTarget|None}.
    """
    multiplier = Decimal(member_count or 1)
    by_day = {
        day: {
            'expected': expected_macros_for_day(targets_by_day.get(day), member_count),
            'effective': empty_macros(),
        }
        for day in _DAYS
    }
    for slot in slots_with_meal:
        household_plate = scale_macros(plate_macros_for_meal(slot.meal), multiplier)
        by_day[slot.day]['effective'] = sum_macros(
            by_day[slot.day]['effective'], household_plate
        )
    return {
        'by_day': by_day,
        'by_week': _week_rollups(by_day),
    }


def _week_rollups(by_day):
    week_expected = None
    week_effective = empty_macros()
    for day in _DAYS:
        entry = by_day[day]
        if entry['expected'] is not None:
            week_expected = sum_macros(week_expected or empty_macros(), entry['expected'])
        week_effective = sum_macros(week_effective, entry['effective'])
    return {'expected': week_expected, 'effective': week_effective}


def build_today_slots(meal_slots, assigned_slots, member_count):
    multiplier = Decimal(member_count)
    today_slots = []
    day_effective = None
    for meal_slot in meal_slots:
        plan_slot = assigned_slots.get(meal_slot.id)
        meal = plan_slot.meal if plan_slot else None
        breakdown = meal_breakdown(meal)
        items = [
            {**item, 'household_grams': item['grams'] * multiplier}
            for item in breakdown['items']
        ]
        plate = breakdown['macros']
        household_macros = scale_macros(plate, multiplier)
        if meal is not None:
            day_effective = (
                household_macros
                if day_effective is None
                else sum_macros(day_effective, household_macros)
            )
        today_slots.append(
            {
                'slot': meal_slot,
                'meal': meal,
                'genre': plan_slot.genre if plan_slot else '',
                'genre_label': _genre_label(plan_slot),
                'items': items,
                'macros': plate,
                'household_macros': household_macros,
            }
        )
    return today_slots, day_effective


def _genre_label(plan_slot):
    if plan_slot is None or not plan_slot.genre:
        return ''
    try:
        return MealGenre(plan_slot.genre).label
    except ValueError:
        return plan_slot.genre

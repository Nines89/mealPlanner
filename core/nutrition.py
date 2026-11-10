"""
Week-plan nutrition totals for a shared household plate.

Expected: ON/OFF target for that weekday × household size.
Effective: macros of each assigned meal's grams × household size.
"""
from decimal import Decimal

from .macros import GRAMS_PER_100, empty_macros, scale_macros, sum_macros
from .models import MealGenre
from .planning import slot_budget  # nuovo import in testa al file
from .quantities import format_ingredient_quantity

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
        'ingredient': ingredient,
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


def expected_macros_for_day(nutrition_target, member_count, skipped_meal_slots=None, all_slots=None):
    """Household expected macros for one day, minus any slot marked 'no meal planned'."""
    if nutrition_target is None:
        return None
    multiplier = Decimal(member_count or 1)
    expected = {
        'kcal': Decimal(nutrition_target.target_kcal) * multiplier,
        'protein': Decimal(nutrition_target.target_protein) * multiplier,
        'carbs': Decimal(nutrition_target.target_carbs) * multiplier,
        'fat': Decimal(nutrition_target.target_fat) * multiplier,
    }
    if not skipped_meal_slots:
        return expected
    for meal_slot in skipped_meal_slots:
        budget = slot_budget(nutrition_target, meal_slot, all_slots or skipped_meal_slots)
        if not budget:
            continue
        for name, amount in budget.items():
            expected[name] = max(Decimal('0'), expected[name] - Decimal(amount) * multiplier)
    return expected


def compute_week_totals(targets_by_day, slots_with_meal, member_count,
                         skipped_slots_by_day=None, all_meal_slots=None):
    multiplier = Decimal(member_count or 1)
    skipped_slots_by_day = skipped_slots_by_day or {}
    by_day = {
        day: {
            'expected': expected_macros_for_day(
                targets_by_day.get(day),
                member_count,
                skipped_meal_slots=skipped_slots_by_day.get(day),
                all_slots=all_meal_slots,
            ),
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
            {
                **item,
                'household_grams': item['grams'] * multiplier,
                'quantity': format_ingredient_quantity(item['ingredient'], item['grams']),
                'household_quantity': format_ingredient_quantity(
                    item['ingredient'], item['grams'] * multiplier
                ),
            }
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
                'skipped': bool(plan_slot and plan_slot.skipped),
                'items': items,
                'macros': plate,
                'household_macros': household_macros,
            }
        )
    return today_slots, day_effective


def add_weekly_ingredient_percentages(today_slots, week_slots, today_day):
    """Add each meal ingredient's share of the quantity still planned that week."""
    weekly_totals = {}
    for slot in week_slots:
        if slot.skipped or slot.meal is None:
            continue
        for row in slot.meal.meal_ingredients.all():
            weekly_totals[row.ingredient_id] = (
                weekly_totals.get(row.ingredient_id, Decimal('0')) + Decimal(row.grams)
            )

    consumed_before = {}
    today_by_id = {
        slot.meal_slot_id: slot for slot in week_slots if slot.day == today_day
    }
    for slot in week_slots:
        if slot.skipped or slot.meal is None:
            continue
        for row in slot.meal.meal_ingredients.all():
            total = weekly_totals[row.ingredient_id]
            remaining = total - consumed_before.get(row.ingredient_id, Decimal('0'))
            if slot.day == today_day and slot.meal_slot_id in today_by_id:
                today_slot = today_by_id[slot.meal_slot_id]
                if today_slot.meal_id == slot.meal_id:
                    current_items = next(
                        (row['items'] for row in today_slots
                         if row['slot'].id == slot.meal_slot_id),
                        [],
                    )
                    for item in current_items:
                        if item['ingredient'].id == row.ingredient_id and 'weekly_percent' not in item:
                            item['weekly_percent'] = min(
                                Decimal('100'), Decimal(row.grams) * 100 / remaining
                            ) if remaining > 0 else Decimal('100')
                            break
            consumed_before[row.ingredient_id] = (
                consumed_before.get(row.ingredient_id, Decimal('0')) + Decimal(row.grams)
            )


def _genre_label(plan_slot):
    if plan_slot is None or not plan_slot.genre:
        return ''
    try:
        return MealGenre(plan_slot.genre).label
    except ValueError:
        return plan_slot.genre


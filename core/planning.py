"""
Fixed-rule portioning from the day's ON/OFF plan. No ML.

Lunch and dinner are each scaled to their slot share, then jointly fitted so
combined macros land in 85–100% of that day's target. Recipe grams are ignored.
Vegetables take leftover kcal and never go below 150 g per item (edible side).
All portion grams are rounded to the nearest whole gram.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .macros import MACRO_NAMES, empty_macros, macros_for_grams, sum_macros
from .models import (
    DietStyle,
    Ingredient,
    IngredientCategory,
    MealSlotTarget,
)

GRAMS_QUANTIZE = Decimal('1')
MIN_GRAMS = Decimal('5')
VEG_MIN_GRAMS = Decimal('150')
MAX_GRAMS = Decimal('9999')
MIN_DAY_COVERAGE = Decimal('0.85')
MAX_DAY_COVERAGE = Decimal('1.00')
_COVERAGE_AIM = (MIN_DAY_COVERAGE + MAX_DAY_COVERAGE) / Decimal('2')
_COVERAGE_EPS = Decimal('0.002')
GENERATED_MEAL_MARKER = 'generated-by-filler'

FILL_SEMI_MANUAL = 'semi_manual'
FILL_SEMI_AUTO = 'semi_auto'
FILL_AUTOMATIC = 'automatic'

DEFAULT_SHARES = {
    1: [Decimal('1.00')],
    2: [Decimal('0.50'), Decimal('0.50')],
}

_VEGAN_TAG_NAMES = ('vegan', 'vegano')
_VEGETARIAN_TAG_NAMES = ('vegetarian', 'vegetariano', 'vegan', 'vegano')
_TARGET_FIELD = {
    'kcal': 'target_kcal',
    'protein': 'target_protein',
    'carbs': 'target_carbs',
    'fat': 'target_fat',
}
_WEEKDAY_SHORT = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


@dataclass(frozen=True)
class PlateSelection:
    protein: object
    vegetable: object
    carb: object | None = None
    fat: object | None = None


def quantize_grams(grams, minimum=None):
    grams = Decimal(grams)
    floor = MIN_GRAMS if minimum is None else minimum
    if grams < floor:
        grams = floor
    if grams > MAX_GRAMS:
        grams = MAX_GRAMS
    return grams.quantize(GRAMS_QUANTIZE, rounding=ROUND_HALF_UP)


def _minimum_grams(ingredient, macro_name=None):
    if macro_name == 'kcal':
        return VEG_MIN_GRAMS
    if getattr(ingredient, 'category', None) == IngredientCategory.VEGETABLE:
        return VEG_MIN_GRAMS
    return MIN_GRAMS


def grams_to_hit_macro(ingredient, macro_name, target_amount):
    per_100 = Decimal(getattr(ingredient, macro_name))
    target_amount = Decimal(target_amount)
    if per_100 <= 0 or target_amount <= 0:
        return None
    return quantize_grams(
        target_amount * Decimal('100') / per_100,
        minimum=_minimum_grams(ingredient, macro_name),
    )


def slot_share(meal_slot, all_slots, nutrition_target=None):
    """
    Fraction of the daily target for this slot.
    Prefers MealSlotTarget.percentage; otherwise hardcoded shares by slot count.
    """
    stored = _stored_slot_share(nutrition_target, meal_slot)
    if stored is not None:
        return stored
    slots = sorted(all_slots, key=lambda slot: (slot.order, slot.id))
    count = len(slots) or 1
    shares = DEFAULT_SHARES.get(count)
    if shares is None:
        equal = (Decimal('1') / Decimal(count)).quantize(Decimal('0.0001'))
        shares = [equal] * count
    try:
        index = [slot.id for slot in slots].index(meal_slot.id)
    except ValueError:
        index = 0
    return shares[min(index, len(shares) - 1)]


def _stored_slot_share(nutrition_target, meal_slot):
    if nutrition_target is None:
        return None
    row = (
        MealSlotTarget.objects.filter(
            nutrition_target=nutrition_target,
            meal_slot=meal_slot,
        )
        .only('percentage')
        .first()
    )
    if row is None or row.percentage is None:
        return None
    return Decimal(row.percentage) / Decimal('100')


def slot_budget(nutrition_target, meal_slot, all_slots):
    """Absolute macro budget for one slot (one plate)."""
    if nutrition_target is None:
        return None
    row = MealSlotTarget.objects.filter(
        nutrition_target=nutrition_target,
        meal_slot=meal_slot,
    ).first()
    if _slot_row_has_macros(row):
        return _budget_from_slot_row(row, nutrition_target)
    share = slot_share(meal_slot, all_slots, nutrition_target)
    return _budget_from_daily_target(nutrition_target, share)


def _slot_row_has_macros(row):
    return row is not None and any(getattr(row, name) is not None for name in MACRO_NAMES)


def _budget_from_daily_target(nutrition_target, share):
    return {
        name: Decimal(getattr(nutrition_target, field)) * share
        for name, field in _TARGET_FIELD.items()
    }


def _budget_from_slot_row(row, nutrition_target):
    share = (
        Decimal(row.percentage) / Decimal('100')
        if row.percentage is not None
        else None
    )
    return {
        name: Decimal(_slot_macro_amount(row, nutrition_target, name, share))
        for name in MACRO_NAMES
    }


def _slot_macro_amount(row, nutrition_target, name, share):
    stored = getattr(row, name)
    if stored is not None:
        return stored
    if share is None:
        return 0
    return Decimal(getattr(nutrition_target, _TARGET_FIELD[name])) * share


def daily_macros(nutrition_target):
    return {
        name: Decimal(getattr(nutrition_target, field))
        for name, field in _TARGET_FIELD.items()
    }


def scale_plate(budget, selection):
    """Grams from the slot budget: protein, remaining carbs, remaining fat, leftover kcal."""
    groups = [
        ('protein', [selection.protein]),
        ('carbs', [selection.carb] if selection.carb else []),
        ('fat', [selection.fat] if selection.fat else []),
        ('kcal', [selection.vegetable]),
    ]
    return _scale_groups(budget, groups)


def scale_ingredients_to_budget(budget, ingredients):
    """Category-based grams from the slot budget. Stored recipe grams are ignored."""
    grouped = _group_by_category(ingredients)
    groups = [
        ('protein', grouped[IngredientCategory.PROTEIN]),
        ('protein', grouped[IngredientCategory.DAIRY]),
        ('carbs', grouped[IngredientCategory.CARB]),
        ('carbs', grouped[IngredientCategory.FRUIT]),
        ('fat', grouped[IngredientCategory.FAT]),
        ('kcal', grouped[IngredientCategory.VEGETABLE]),
    ]
    items = _scale_groups(budget, groups)
    items.extend(
        (ingredient, MIN_GRAMS) for ingredient in grouped[IngredientCategory.OTHER]
    )
    return items


def scale_day_meals(nutrition_target, all_slots, sources):
    """
    Scale each slot from the plan, then fit lunch+dinner into 85–100% of the day.

    ``sources`` is a list of ``(meal_slot, name, genre, ingredients)``.
    """
    plates = []
    for meal_slot, name, genre, ingredients in sources:
        budget = slot_budget(nutrition_target, meal_slot, all_slots)
        items = scale_ingredients_to_budget(budget, ingredients)
        plates.append((meal_slot, name, genre, items))
    fitted = fit_day_coverage(
        daily_macros(nutrition_target),
        [row[3] for row in plates],
    )
    return [
        (slot, name, genre, items)
        for (slot, name, genre, _), items in zip(plates, fitted)
    ]


def _apply_gram_factor(items, factor):
    return [
        (ingredient, quantize_grams(grams * factor, minimum=_minimum_grams(ingredient)))
        for ingredient, grams in items
    ]


def _cap_kcal(plates, daily):
    combined = _combined_plate_macros(plates)['kcal']
    limit = daily['kcal'] * MAX_DAY_COVERAGE
    if combined <= limit + daily['kcal'] * _COVERAGE_EPS:
        return plates
    return [_apply_gram_factor(plate, limit / combined) for plate in plates]


def fit_day_coverage(daily, plates):
    """Scale plates so combined macros land in 85–100% of the daily target."""
    if len(plates) < 2:
        return plates
    plates = _aim_category(plates, IngredientCategory.CARB, 'carbs', daily)
    plates = _aim_category(plates, IngredientCategory.FRUIT, 'carbs', daily)
    plates = _aim_category(plates, IngredientCategory.FAT, 'fat', daily)
    plates = _lift_kcal(plates, daily)
    plates = _cap_macros(plates, daily)
    plates = _ensure_kcal_floor(plates, daily)
    return _cap_kcal(plates, daily)


def _aim_category(plates, category, macro_name, daily, aim=None, shrink_if_unneeded=False):
    target_share = _COVERAGE_AIM if aim is None else aim
    combined = _combined_plate_macros(plates)[macro_name]
    from_cat = _category_macro(plates, category, macro_name)
    if from_cat <= 0:
        return plates
    needed = daily[macro_name] * target_share - (combined - from_cat)
    if needed <= 0:
        if shrink_if_unneeded:
            return _scale_category_grams(plates, category, Decimal('0'))
        return plates
    return _scale_category_grams(plates, category, needed / from_cat)


def _lift_kcal(plates, daily):
    """Grow vegetables, fat, then carbs until calories reach the mid-band."""
    target = daily['kcal'] * _COVERAGE_AIM
    for category in (
        IngredientCategory.VEGETABLE,
        IngredientCategory.FAT,
        IngredientCategory.CARB,
    ):
        if _combined_plate_macros(plates)['kcal'] >= target:
            return plates
        plates = _aim_category(plates, category, 'kcal', daily, _COVERAGE_AIM)
    return plates


def _cap_macros(plates, daily):
    plates = _cap_cascade(
        plates, 'protein', daily,
        (IngredientCategory.DAIRY, IngredientCategory.PROTEIN),
    )
    plates = _cap_cascade(
        plates, 'carbs', daily,
        (IngredientCategory.FRUIT, IngredientCategory.CARB),
    )
    plates = _cap_cascade(
        plates, 'fat', daily,
        (IngredientCategory.FAT,),
    )
    return _cap_cascade(
        plates, 'kcal', daily,
        (IngredientCategory.FAT, IngredientCategory.CARB),
    )


def _cap_cascade(plates, macro_name, daily, categories):
    limit = daily[macro_name] * MAX_DAY_COVERAGE
    slack = daily[macro_name] * _COVERAGE_EPS
    for category in categories:
        combined = _combined_plate_macros(plates)[macro_name]
        if combined <= limit + slack:
            return plates
        plates = _aim_category(
            plates, category, macro_name, daily, MAX_DAY_COVERAGE, shrink_if_unneeded=True
        )
    return plates


def _ensure_kcal_floor(plates, daily):
    target = daily['kcal'] * MIN_DAY_COVERAGE
    combined = _combined_plate_macros(plates)
    if combined['kcal'] >= target or combined['kcal'] <= 0:
        return plates
    energy_cats = (
        IngredientCategory.VEGETABLE,
        IngredientCategory.CARB,
        IngredientCategory.FAT,
    )
    energy = sum(
        (_category_macro(plates, category, 'kcal') for category in energy_cats),
        Decimal('0'),
    )
    if energy <= 0:
        return plates
    factor = (energy + target - combined['kcal']) / energy
    for category in energy_cats:
        plates = _scale_category_grams(plates, category, factor)
    return plates


def _category_macro(plates, category, macro_name):
    total = Decimal('0')
    for plate in plates:
        for ingredient, grams in plate:
            if getattr(ingredient, 'category', None) != category:
                continue
            total += macros_for_grams(ingredient, grams)[macro_name]
    return total


def _scale_category_grams(plates, category, factor):
    scaled = []
    for plate in plates:
        scaled.append(
            [
                (
                    ingredient,
                    quantize_grams(
                        grams * factor,
                        minimum=_minimum_grams(ingredient),
                    )
                    if getattr(ingredient, 'category', None) == category
                    else grams,
                )
                for ingredient, grams in plate
            ]
        )
    return scaled


def _group_by_category(ingredients):
    grouped = defaultdict(list)
    for ingredient in ingredients:
        category = getattr(ingredient, 'category', None) or IngredientCategory.OTHER
        grouped[category].append(ingredient)
    return grouped


def _scale_groups(budget, groups):
    items = []
    current = empty_macros()
    for macro_name, ingredients in groups:
        if not ingredients:
            continue
        remaining = budget[macro_name] - current[macro_name]
        chunk, current = _scale_group_to_macro(
            ingredients, macro_name, remaining, current
        )
        items.extend(chunk)
    return items


def _scale_group_to_macro(ingredients, macro_name, remaining, current):
    usable, unusable = _split_by_macro(ingredients, macro_name)
    items = []
    running = current
    if usable and remaining > 0:
        share = remaining / Decimal(len(usable))
        for ingredient in usable:
            floor = _minimum_grams(ingredient, macro_name)
            grams = grams_to_hit_macro(ingredient, macro_name, share) or floor
            items.append((ingredient, grams))
            running = sum_macros(running, macros_for_grams(ingredient, grams))
    else:
        for ingredient in usable:
            floor = _minimum_grams(ingredient, macro_name)
            items.append((ingredient, floor))
            running = sum_macros(running, macros_for_grams(ingredient, floor))
    for ingredient in unusable:
        floor = _minimum_grams(ingredient, macro_name)
        items.append((ingredient, floor))
        running = sum_macros(running, macros_for_grams(ingredient, floor))
    return items, running


def _split_by_macro(ingredients, macro_name):
    usable = []
    unusable = []
    for ingredient in ingredients:
        if Decimal(getattr(ingredient, macro_name)) > 0:
            usable.append(ingredient)
        else:
            unusable.append(ingredient)
    return usable, unusable


def _combined_plate_macros(plates):
    total = empty_macros()
    for plate in plates:
        total = sum_macros(total, _items_macros(plate))
    return total


def _items_macros(items):
    total = empty_macros()
    for ingredient, grams in items:
        total = sum_macros(total, macros_for_grams(ingredient, grams))
    return total


def _tag_names_for_diet(diet_style):
    if diet_style == DietStyle.VEGAN:
        return _VEGAN_TAG_NAMES
    if diet_style == DietStyle.VEGETARIAN:
        return _VEGETARIAN_TAG_NAMES
    return ()


def apply_diet_filter(queryset, diet_style):
    """Light diet filter: vegan drops dairy; tagged vegan/vegetarian protein if tags exist."""
    if not diet_style or diet_style == DietStyle.NONE:
        return queryset
    filtered = queryset
    if diet_style == DietStyle.VEGAN:
        filtered = filtered.exclude(category=IngredientCategory.DAIRY)
    tag_names = _tag_names_for_diet(diet_style)
    if not tag_names:
        return filtered.distinct()
    tagged_protein_exists = Ingredient.objects.filter(
        category=IngredientCategory.PROTEIN,
        tags__name__in=tag_names,
    ).exists()
    if not tagged_protein_exists:
        return filtered.distinct()
    proteins = filtered.filter(category=IngredientCategory.PROTEIN, tags__name__in=tag_names)
    rest = filtered.exclude(category=IngredientCategory.PROTEIN)
    return (proteins | rest).distinct()


def ingredients_for_category(category, diet_style=None):
    queryset = Ingredient.objects.filter(category=category).order_by('name')
    return apply_diet_filter(queryset, diet_style)


def pick_random_vegetable(diet_style=None, vegetable_subcategory=''):
    queryset = ingredients_for_category(IngredientCategory.VEGETABLE, diet_style)
    if vegetable_subcategory:
        narrowed = queryset.filter(vegetable_subcategory=vegetable_subcategory)
        if narrowed.exists():
            queryset = narrowed
    return queryset.order_by('?').first()


def pick_random_protein(diet_style=None):
    queryset = ingredients_for_category(IngredientCategory.PROTEIN, diet_style)
    return queryset.order_by('?').first()


def _pick_both(_protein, _vegetable, diet_style):
    return pick_random_protein(diet_style), pick_random_vegetable(diet_style)


def _pick_vegetable(protein, _vegetable, diet_style):
    return protein, pick_random_vegetable(diet_style)


def _keep_selection(protein, vegetable, _diet_style):
    return protein, vegetable


_FILL_INGREDIENT_RESOLVERS = {
    FILL_AUTOMATIC: _pick_both,
    FILL_SEMI_AUTO: _pick_vegetable,
    FILL_SEMI_MANUAL: _keep_selection,
}


def resolve_fill_ingredients(mode, protein, vegetable, diet_style):
    resolver = _FILL_INGREDIENT_RESOLVERS.get(mode, _keep_selection)
    return resolver(protein, vegetable, diet_style)


def weekday_short_label(day):
    if 0 <= day < 7:
        return _WEEKDAY_SHORT[day]
    return str(day)


def generated_meal_name(day, meal_slot):
    return f'{weekday_short_label(day)} {meal_slot.name}'[:100]


def shopping_list_for_plan(week_plan, member_count):
    """
    Aggregate plate grams across the week, multiplied by household size.
    Returns a list of dicts: name, grams, ingredient.
    """
    multiplier = Decimal(member_count or 1)
    totals = defaultdict(lambda: Decimal('0'))
    ingredients = {}
    slots = week_plan.slots.select_related('meal').prefetch_related(
        'meal__meal_ingredients__ingredient'
    )
    for slot in slots:
        if slot.meal_id is None:
            continue
        for meal_ingredient in slot.meal.meal_ingredients.all():
            totals[meal_ingredient.ingredient_id] += Decimal(meal_ingredient.grams) * multiplier
            ingredients[meal_ingredient.ingredient_id] = meal_ingredient.ingredient
    rows = [
        {
            'ingredient': ingredients[ingredient_id],
            'name': ingredients[ingredient_id].name,
            'grams': quantize_grams(grams),
        }
        for ingredient_id, grams in totals.items()
    ]
    rows.sort(key=lambda row: row['name'].lower())
    return rows

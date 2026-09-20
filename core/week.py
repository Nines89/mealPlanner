"""Current-week plan: retrieve, grid, ON/OFF days, random dish from category."""
from dataclasses import dataclass
from datetime import date, timedelta
from random import choice

from django.db.models import Q

from .models import (
    DayKind,
    Household,
    Meal,
    MealGenre,
    MealIngredient,
    MealSlot,
    IngredientCategory,
    WeekDay,
    WeekPlan,
    WeekPlanDayKind,
    WeekPlanSlot,
)
from .nutrition import compute_week_totals, plate_macros_for_meal
from .planning import (
    GENERATED_MEAL_MARKER,
    generated_meal_name,
    resolve_fill_ingredients,
    scale_day_meals,
    slot_budget,
)
from .targets import get_target_by_kind, targets_by_day

WEEK_DAYS = range(7)


def monday_of_week(for_date=None):
    """Monday of the ISO week that contains ``for_date`` (default: today)."""
    day = for_date or date.today()
    return day - timedelta(days=day.weekday())


def week_plan_for_monday(user, monday):
    return WeekPlan.objects.filter(owner=user, week_start=monday).first()


def get_current_week_plan(user):
    monday = monday_of_week()
    off_target = get_target_by_kind(DayKind.OFF)
    week_plan, _created = WeekPlan.objects.get_or_create(
        owner=user,
        week_start=monday,
        defaults={'is_system': False, 'nutrition_target': off_target},
    )
    return week_plan, monday


_VALID_GENRES = {value for value, _label in MealGenre.choices}


def save_day_kinds(week_plan, post_data):
    for day in WEEK_DAYS:
        raw = post_data.get(f'day_kind_{day}', DayKind.OFF).strip().lower()
        kind = DayKind.ON if raw == DayKind.ON else DayKind.OFF
        WeekPlanDayKind.objects.update_or_create(
            week_plan=week_plan,
            day=day,
            defaults={'kind': kind},
        )


@dataclass(frozen=True)
class GridSaveResult:
    updated: int
    removed: int
    invalid: int


@dataclass(frozen=True)
class RebuildSlotResult:
    dish_name: str
    previous_name: str
    missing: bool


def save_genre_grid(week_plan, meal_slots, post_data):
    existing_slots = {
        (slot.day, slot.meal_slot_id): slot
        for slot in WeekPlanSlot.objects.filter(week_plan=week_plan).select_related('meal')
    }
    updated = removed = invalid = 0
    for meal_slot in meal_slots:
        for day in WEEK_DAYS:
            raw_genre = post_data.get(f'genre_{day}_{meal_slot.id}', '').strip()
            existing = existing_slots.get((day, meal_slot.id))
            genre, parse_error = _parse_posted_genre(raw_genre)
            if parse_error:
                invalid += 1
                continue
            action = _assign_grid_genre(week_plan, day, meal_slot, existing, genre)
            if action == 'updated':
                updated += 1
            elif action == 'removed':
                removed += 1
    return GridSaveResult(updated=updated, removed=removed, invalid=invalid)


def _parse_posted_genre(raw_genre):
    if not raw_genre:
        return '', False
    if raw_genre not in _VALID_GENRES:
        return '', True
    return raw_genre, False


def _assign_grid_genre(week_plan, day, meal_slot, existing_slot, genre):
    if not genre:
        return _clear_grid_cell(week_plan, existing_slot)
    if existing_slot is None:
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=day,
            meal_slot=meal_slot,
            genre=genre,
            meal=None,
        )
        return 'updated'
    return _update_grid_genre(week_plan, existing_slot, genre)


def _clear_grid_cell(week_plan, existing_slot):
    if existing_slot is None:
        return 'skipped'
    old_meal = existing_slot.meal
    existing_slot.delete()
    _delete_orphan_generated_meal(old_meal, week_plan.owner_id)
    return 'removed'


def _update_grid_genre(week_plan, existing_slot, genre):
    meal = existing_slot.meal
    meal_matches = meal is not None and meal.genre == genre
    if existing_slot.genre == genre and (meal is None or meal_matches):
        return 'skipped'
    old_meal = None if meal_matches else meal
    existing_slot.genre = genre
    existing_slot.meal = meal if meal_matches else None
    existing_slot.save(update_fields=['genre', 'meal'])
    _delete_orphan_generated_meal(old_meal, week_plan.owner_id)
    return 'updated'


def catalog_meals_for(user):
    return Meal.objects.filter(Q(is_system=True) | Q(owner=user)).exclude(
        description=GENERATED_MEAL_MARKER,
    )


def rescale_assigned_portions(week_plan, meal_slots):
    """Keep assigned dishes; recompute grams from each day's ON/OFF target."""
    for day, sources in _assigned_sources_by_day(week_plan).items():
        _write_scaled_day(week_plan, day, sources, meal_slots)


def _assigned_sources_by_day(week_plan):
    grouped = {}
    queryset = (
        WeekPlanSlot.objects.filter(week_plan=week_plan, meal__isnull=False)
        .select_related('meal', 'meal_slot')
        .prefetch_related('meal__meal_ingredients__ingredient')
        .order_by('day', 'meal_slot__order')
    )
    for plan_slot in queryset:
        ingredients = [row.ingredient for row in plan_slot.meal.meal_ingredients.all()]
        if not ingredients:
            continue
        grouped.setdefault(plan_slot.day, []).append(
            (
                plan_slot.meal_slot,
                plan_slot.meal.name,
                plan_slot.genre or plan_slot.meal.genre or '',
                ingredients,
            )
        )
    return grouped


def assign_random_meals(week_plan, meal_slots):
    """Fill slots that have a category but no dish. Keep recipes already assigned."""
    pools = _meal_pools_by_genre(week_plan.owner)
    used_ids = _used_catalog_ids(week_plan, pools)
    assigned = missing = 0
    picks_by_day = {day: [] for day in WEEK_DAYS}
    dirty_days = set()
    slots = {
        (slot.day, slot.meal_slot_id): slot
        for slot in WeekPlanSlot.objects.filter(week_plan=week_plan).select_related('meal')
    }
    for meal_slot in meal_slots:
        for day in WEEK_DAYS:
            plan_slot = slots.get((day, meal_slot.id))
            if plan_slot is None or not plan_slot.genre:
                continue
            source, action = _source_for_build(plan_slot, meal_slot, pools, used_ids)
            if source is None:
                missing += 1
                continue
            picks_by_day[day].append(source)
            if action == 'assigned':
                assigned += 1
                dirty_days.add(day)
    for day in dirty_days:
        _write_scaled_day(week_plan, day, picks_by_day[day], meal_slots)
    return GridSaveResult(updated=assigned, removed=0, invalid=missing)


def _source_for_build(plan_slot, meal_slot, pools, used_ids):
    if _ingredients_of(plan_slot.meal):
        return _source_from_slot(plan_slot, meal_slot), 'kept'
    meal = _pick_from_pool(pools.get(plan_slot.genre, ()), used_ids)
    ingredients = _ingredients_of(meal)
    if meal is None or not ingredients:
        return None, 'missing'
    used_ids.add(meal.id)
    return (meal_slot, meal.name, meal.genre, ingredients), 'assigned'


def _source_from_slot(plan_slot, meal_slot):
    meal = plan_slot.meal
    return (
        meal_slot,
        meal.name,
        plan_slot.genre or meal.genre or '',
        _ingredients_of(meal),
    )


def _used_catalog_ids(week_plan, pools):
    names = set(
        WeekPlanSlot.objects.filter(week_plan=week_plan, meal__isnull=False).values_list(
            'meal__name', flat=True
        )
    )
    return {
        meal.id
        for pool in pools.values()
        for meal in pool
        if meal.name in names
    }


def _meal_pools_by_genre(user):
    pools = {value: [] for value in _VALID_GENRES}
    queryset = catalog_meals_for(user).filter(genre__in=_VALID_GENRES).order_by('id')
    for meal in queryset:
        pools[meal.genre].append(meal)
    return pools


def _pick_from_pool(pool, used_ids, skip_names=None):
    if not pool:
        return None
    skip_names = set(skip_names or ())
    preferred = [
        meal for meal in pool if meal.id not in used_ids and meal.name not in skip_names
    ]
    if preferred:
        return choice(preferred)
    others = [meal for meal in pool if meal.name not in skip_names]
    return choice(others or pool)


def rebuild_slot_meal(week_plan, meal_slots, day, meal_slot):
    """Pick a new catalog dish for one cell; keep the rest of that day."""
    plan_slot = _plan_slot_on(week_plan, day, meal_slot)
    previous = plan_slot.meal.name if plan_slot and plan_slot.meal else ''
    if plan_slot is None or not plan_slot.genre:
        return RebuildSlotResult('', previous, True)
    meal = _replacement_catalog_meal(week_plan, plan_slot)
    if meal is None or not _ingredients_of(meal):
        return RebuildSlotResult('', previous, True)
    sources = _day_sources_for_rebuild(week_plan, day, meal_slots, (meal_slot.id, meal))
    _write_scaled_day(week_plan, day, sources, meal_slots)
    return RebuildSlotResult(meal.name, previous, False)


def _plan_slot_on(week_plan, day, meal_slot):
    return (
        WeekPlanSlot.objects.filter(week_plan=week_plan, day=day, meal_slot=meal_slot)
        .select_related('meal')
        .first()
    )


def _replacement_catalog_meal(week_plan, plan_slot):
    pools = _meal_pools_by_genre(week_plan.owner)
    used_ids = _used_catalog_ids(week_plan, pools)
    current_name = plan_slot.meal.name if plan_slot.meal else ''
    return _pick_from_pool(pools.get(plan_slot.genre, ()), used_ids, {current_name})


def _day_sources_for_rebuild(week_plan, day, meal_slots, pick):
    focus_id, meal = pick
    ingredients = _ingredients_of(meal)
    existing = {
        slot.meal_slot_id: slot
        for slot in WeekPlanSlot.objects.filter(week_plan=week_plan, day=day).select_related(
            'meal'
        )
    }
    sources = []
    for slot in meal_slots:
        if slot.id == focus_id:
            sources.append((slot, meal.name, meal.genre, ingredients))
            continue
        other = existing.get(slot.id)
        if other is not None and _ingredients_of(other.meal):
            sources.append(_source_from_slot(other, slot))
    return sources


def replace_slot_meal(week_plan, day, meal_slot, new_meal):
    existing = (
        WeekPlanSlot.objects.filter(week_plan=week_plan, day=day, meal_slot=meal_slot)
        .select_related('meal')
        .first()
    )
    old_meal = existing.meal if existing else None
    genre = _genre_for_replaced_meal(existing, new_meal)
    if new_meal.genre != genre:
        new_meal.genre = genre
        new_meal.save(update_fields=['genre'])
    if existing:
        existing.meal = new_meal
        existing.genre = genre
        existing.save(update_fields=['meal', 'genre'])
    else:
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=day,
            meal_slot=meal_slot,
            meal=new_meal,
            genre=genre,
        )
    _delete_orphan_generated_meal(old_meal, week_plan.owner_id)


def _genre_for_replaced_meal(existing, new_meal):
    if existing is not None and existing.genre:
        return existing.genre
    return new_meal.genre or ''


def _delete_orphan_generated_meal(old_meal, owner_id):
    if old_meal is None:
        return
    if old_meal.description != GENERATED_MEAL_MARKER:
        return
    if old_meal.owner_id != owner_id:
        return
    if old_meal.slots.exists():
        return
    old_meal.delete()


def week_plan_slots(week_plan):
    return list(
        WeekPlanSlot.objects.filter(week_plan=week_plan)
        .select_related('meal_slot', 'meal')
        .prefetch_related('meal__meal_ingredients__ingredient')
        .order_by('day', 'meal_slot__order')
    )


def grid_rows_for(meal_slots, slots_list):
    by_day_slot = {(slot.day, slot.meal_slot_id): slot for slot in slots_list}
    rows = []
    for slot in meal_slots:
        cells = [_grid_cell(day, by_day_slot.get((day, slot.id))) for day in WEEK_DAYS]
        rows.append({'slot': slot, 'cells': cells})
    return rows


def _grid_cell(day, plan_slot):
    genre = plan_slot.genre if plan_slot else ''
    meal = plan_slot.meal if plan_slot else None
    return {
        'day': day,
        'genre': genre,
        'genre_label': _genre_display(genre),
        'meal': meal,
        'preview': _meal_preview_items(meal),
        'kcal': _meal_kcal(meal),
    }


def _meal_preview_items(meal, limit=3):
    if meal is None:
        return []
    items = []
    rows = list(meal.meal_ingredients.all())
    # Always include the suggested vegetable in the compact card preview so
    # the display-mode selector has a visible effect.
    rows.sort(
        key=lambda row: row.ingredient.category != IngredientCategory.VEGETABLE
    )
    for row in rows:
        ingredient = row.ingredient
        items.append(
            {
                'name': ingredient.name,
                'vegetable_macro_category': _vegetable_macro_category(ingredient),
                'grams': row.grams,
            }
        )
        if len(items) == limit:
            break
    return items


def _vegetable_macro_category(ingredient):
    if ingredient.category != IngredientCategory.VEGETABLE:
        return ''
    return ingredient.get_vegetable_subcategory_display()


def _meal_kcal(meal):
    if meal is None:
        return None
    return plate_macros_for_meal(meal)['kcal']


def _genre_display(genre):
    if not genre:
        return ''
    try:
        return MealGenre(genre).label
    except ValueError:
        return genre


def day_kind_columns(week_plan, monday=None):
    today = date.today()
    monday = monday or week_plan.week_start
    day_targets = targets_by_day(week_plan)
    return [
        _day_kind_column(day, day_targets.get(day), monday, today)
        for day in WEEK_DAYS
    ]


def _day_kind_column(day, target, monday, today):
    kind = target.kind if target else DayKind.OFF
    return {
        'day': day,
        'label': WeekDay(day).label,
        'short_label': WeekDay(day).label[:3],
        'kind': kind,
        'is_today': day == today.weekday(),
        'date': monday + timedelta(days=day) if monday else None,
        'target_kcal': target.target_kcal if target else None,
    }


def board_days_for(day_columns, rows):
    return [_board_day(column, rows) for column in day_columns]


def _board_day(column, rows):
    slots = [
        {'slot': row['slot'], 'cell': row['cells'][column['day']]}
        for row in rows
    ]
    return {**column, 'slots': slots, 'plate_kcal': _plate_kcal_for(slots)}


def _plate_kcal_for(slots):
    total = 0
    for entry in slots:
        kcal = entry['cell'].get('kcal')
        if kcal:
            total += kcal
    return total


def week_plan_page_context(user, week_plan, monday):
    household = Household.ensure_for_user(user)
    members = list(household.members.all())
    member_count = len(members) or 1
    meal_slots = list(MealSlot.objects.filter(user=user).order_by('order'))
    rescale_assigned_portions(week_plan, meal_slots)
    slots_list = week_plan_slots(week_plan)
    day_targets = targets_by_day(week_plan)
    slots_with_meal = [slot for slot in slots_list if slot.meal_id]
    day_columns = day_kind_columns(week_plan, monday)
    grid_rows = grid_rows_for(meal_slots, slots_list)
    return {
        'week_plan': week_plan,
        'week_start': monday,
        'meal_slots': meal_slots,
        'meal_genres': MealGenre.choices,
        'grid_rows': grid_rows,
        'board_days': board_days_for(day_columns, grid_rows),
        'week_day_headers': [(day, WeekDay(day).label) for day in WEEK_DAYS],
        'day_kind_columns': day_columns,
        'household': household,
        'member_count': member_count,
        'nutrition_totals': compute_week_totals(day_targets, slots_with_meal, member_count),
        'on_target': get_target_by_kind(DayKind.ON),
        'off_target': get_target_by_kind(DayKind.OFF),
        'today_weekday': date.today().weekday(),
    }


@dataclass(frozen=True)
class FillPage:
    week_plan: object
    day: int
    meal_slot: object
    budget: dict
    day_target: object

    @property
    def diet_style(self):
        return self.day_target.diet_style

    def template_context(self, form):
        return {
            'form': form,
            'day': self.day,
            'day_label': WeekDay(self.day).label,
            'meal_slot': self.meal_slot,
            'budget': self.budget,
            'active_target': self.day_target,
        }


def load_fill_page(user, day, meal_slot):
    week_plan, _monday = get_current_week_plan(user)
    off_target = get_target_by_kind(DayKind.OFF)
    day_target = targets_by_day(week_plan).get(day) or off_target
    if day_target is None:
        return None
    all_slots = list(MealSlot.objects.filter(user=user).order_by('order'))
    return FillPage(
        week_plan=week_plan,
        day=day,
        meal_slot=meal_slot,
        budget=slot_budget(day_target, meal_slot, all_slots),
        day_target=day_target,
    )


def apply_fill(page, cleaned_form):
    protein, vegetable = resolve_fill_ingredients(
        cleaned_form['mode'],
        cleaned_form.get('protein'),
        cleaned_form.get('vegetable'),
        page.diet_style,
    )
    if protein is None or vegetable is None:
        return None
    ingredients = [protein, vegetable]
    for extra in (cleaned_form.get('carb'), cleaned_form.get('fat')):
        if extra is not None:
            ingredients.append(extra)
    all_slots = list(
        MealSlot.objects.filter(user=page.week_plan.owner).order_by('order')
    )
    sources = _fill_day_sources(page, all_slots, ingredients)
    return _write_scaled_day(
        page.week_plan, page.day, sources, all_slots, focus_slot=page.meal_slot
    )


def _fill_day_sources(page, all_slots, fill_ingredients):
    sources = []
    existing = {
        slot.meal_slot_id: slot
        for slot in WeekPlanSlot.objects.filter(
            week_plan=page.week_plan, day=page.day
        ).select_related('meal')
    }
    for meal_slot in all_slots:
        if meal_slot.id == page.meal_slot.id:
            sources.append(
                (
                    meal_slot,
                    generated_meal_name(page.day, meal_slot),
                    _genre_for_fill(existing.get(meal_slot.id)),
                    fill_ingredients,
                )
            )
            continue
        plan_slot = existing.get(meal_slot.id)
        ingredients = _ingredients_of(plan_slot.meal if plan_slot else None)
        if not ingredients:
            continue
        sources.append(
            (meal_slot, plan_slot.meal.name, plan_slot.meal.genre, ingredients)
        )
    return sources


def _genre_for_fill(plan_slot):
    if plan_slot is None:
        return ''
    return plan_slot.genre or (plan_slot.meal.genre if plan_slot.meal else '')


def _ingredients_of(meal):
    if meal is None:
        return []
    return [
        row.ingredient
        for row in meal.meal_ingredients.select_related('ingredient').all()
    ]


def _write_scaled_day(week_plan, day, sources, all_slots, focus_slot=None):
    day_target = targets_by_day(week_plan).get(day) or get_target_by_kind(DayKind.OFF)
    if day_target is None:
        return None
    written = {}
    for meal_slot, name, genre, items in scale_day_meals(day_target, all_slots, sources):
        meal = _persist_scaled_slot(week_plan, day, meal_slot, name, genre, items)
        written[meal_slot.id] = meal
    if focus_slot is not None:
        return written.get(focus_slot.id)
    return next(iter(written.values()), None)


def _persist_scaled_slot(week_plan, day, meal_slot, name, genre, items):
    existing = (
        WeekPlanSlot.objects.filter(week_plan=week_plan, day=day, meal_slot=meal_slot)
        .select_related('meal')
        .first()
    )
    meal = existing.meal if existing else None
    if _is_owned_generated(meal, week_plan.owner_id):
        _replace_meal_items(meal, items)
        _sync_generated_meal_meta(meal, name, genre)
        return meal
    meal = _create_named_meal(week_plan, name, genre, items)
    replace_slot_meal(week_plan, day, meal_slot, meal)
    return meal


def _is_owned_generated(meal, owner_id):
    return (
        meal is not None
        and not meal.is_system
        and meal.owner_id == owner_id
        and meal.description == GENERATED_MEAL_MARKER
    )


def _replace_meal_items(meal, items):
    meal.meal_ingredients.all().delete()
    MealIngredient.objects.bulk_create(
        [
            MealIngredient(meal=meal, ingredient=ingredient, grams=grams)
            for ingredient, grams in items
        ]
    )


def _sync_generated_meal_meta(meal, name, genre):
    name = name[:100]
    genre = genre or meal.genre or ''
    if meal.name == name and meal.genre == genre:
        return
    meal.name = name
    meal.genre = genre
    meal.save(update_fields=['name', 'genre'])


def _create_named_meal(week_plan, name, genre, items):
    meal = Meal.objects.create(
        owner=week_plan.owner,
        is_system=False,
        name=name[:100],
        genre=genre or '',
        description=GENERATED_MEAL_MARKER,
    )
    MealIngredient.objects.bulk_create(
        [
            MealIngredient(meal=meal, ingredient=ingredient, grams=grams)
            for ingredient, grams in items
        ]
    )
    return meal

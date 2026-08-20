"""Lunch and dinner only — breakfast is not part of the planner."""
from django.contrib.auth.models import User

from .models import MealSlot, MealSlotDefault, MealSlotTarget, WeekPlanSlot

BREAKFAST_NAMES = frozenset({'colazione', 'breakfast'})
LUNCH_NAMES = frozenset({'pranzo', 'lunch'})
DINNER_NAMES = frozenset({'cena', 'dinner'})

LUNCH_DEFAULT_NAME = 'Lunch'
DINNER_DEFAULT_NAME = 'Dinner'


def _norm(name):
    return (name or '').strip().lower()


def is_breakfast_name(name):
    return _norm(name) in BREAKFAST_NAMES


def _has_named(queryset, names):
    return any(_norm(obj.name) in names for obj in queryset)


def sync_lunch_dinner_slots():
    """
    Drop breakfast (Colazione / Breakfast) everywhere and make sure
    lunch + dinner defaults and per-user slots exist.
    """
    if not _needs_sync():
        return
    _delete_breakfast_plan_rows()
    _ensure_default_slots()
    _ensure_user_slots()


def _needs_sync():
    default_names = {_norm(row.name) for row in MealSlotDefault.objects.all()}
    if default_names & BREAKFAST_NAMES:
        return True
    if not (default_names & LUNCH_NAMES) or not (default_names & DINNER_NAMES):
        return True
    slot_names = {_norm(slot.name) for slot in MealSlot.objects.all()}
    if slot_names & BREAKFAST_NAMES:
        return True
    user_count = User.objects.count()
    if user_count and MealSlot.objects.count() < user_count * 2:
        return True
    return False


def _delete_breakfast_plan_rows():
    breakfast_slots = [
        slot for slot in MealSlot.objects.all() if is_breakfast_name(slot.name)
    ]
    breakfast_ids = [slot.id for slot in breakfast_slots]
    if breakfast_ids:
        WeekPlanSlot.objects.filter(meal_slot_id__in=breakfast_ids).delete()
        MealSlotTarget.objects.filter(meal_slot_id__in=breakfast_ids).delete()
        MealSlot.objects.filter(id__in=breakfast_ids).delete()

    breakfast_defaults = [
        row for row in MealSlotDefault.objects.all() if is_breakfast_name(row.name)
    ]
    if breakfast_defaults:
        MealSlotDefault.objects.filter(id__in=[row.id for row in breakfast_defaults]).delete()


def _ensure_default_slots():
    defaults = list(MealSlotDefault.objects.all())
    if not _has_named(defaults, LUNCH_NAMES):
        MealSlotDefault.objects.create(name=LUNCH_DEFAULT_NAME, order=0)
    if not _has_named(list(MealSlotDefault.objects.all()), DINNER_NAMES):
        MealSlotDefault.objects.create(name=DINNER_DEFAULT_NAME, order=1)
    _renumber_defaults()


def _renumber_defaults():
    rows = list(MealSlotDefault.objects.order_by('order', 'id'))
    for i, row in enumerate(rows):
        if row.order != i:
            row.order = i
            row.save(update_fields=['order'])


def _ensure_user_slots():
    defaults = list(MealSlotDefault.objects.order_by('order', 'id'))
    lunch_name = next(
        (row.name for row in defaults if _norm(row.name) in LUNCH_NAMES),
        LUNCH_DEFAULT_NAME,
    )
    dinner_name = next(
        (row.name for row in defaults if _norm(row.name) in DINNER_NAMES),
        DINNER_DEFAULT_NAME,
    )
    for user in User.objects.all():
        slots = list(MealSlot.objects.filter(user=user))
        if not _has_named(slots, LUNCH_NAMES):
            MealSlot.objects.create(user=user, name=lunch_name, order=100)
        if not _has_named(list(MealSlot.objects.filter(user=user)), DINNER_NAMES):
            MealSlot.objects.create(user=user, name=dinner_name, order=101)
        _renumber_user_slots(user)


def _renumber_user_slots(user):
    slots = list(MealSlot.objects.filter(user=user).order_by('order', 'id'))
    for i, slot in enumerate(slots):
        slot.order = 200 + i
        slot.save(update_fields=['order'])
    slots = list(MealSlot.objects.filter(user=user).order_by('order', 'id'))
    for i, slot in enumerate(slots):
        slot.order = i
        slot.save(update_fields=['order'])

from django.db import migrations


BREAKFAST_NAMES = frozenset({'colazione', 'breakfast'})
LUNCH_NAMES = frozenset({'pranzo', 'lunch'})
DINNER_NAMES = frozenset({'cena', 'dinner'})


def _norm(name):
    return (name or '').strip().lower()


def remove_breakfast(apps, schema_editor):
    MealSlot = apps.get_model('core', 'MealSlot')
    MealSlotDefault = apps.get_model('core', 'MealSlotDefault')
    MealSlotTarget = apps.get_model('core', 'MealSlotTarget')
    WeekPlanSlot = apps.get_model('core', 'WeekPlanSlot')
    User = apps.get_model('auth', 'User')

    breakfast_ids = [
        slot.id for slot in MealSlot.objects.all() if _norm(slot.name) in BREAKFAST_NAMES
    ]
    if breakfast_ids:
        WeekPlanSlot.objects.filter(meal_slot_id__in=breakfast_ids).delete()
        MealSlotTarget.objects.filter(meal_slot_id__in=breakfast_ids).delete()
        MealSlot.objects.filter(id__in=breakfast_ids).delete()

    default_ids = [
        row.id for row in MealSlotDefault.objects.all() if _norm(row.name) in BREAKFAST_NAMES
    ]
    if default_ids:
        MealSlotDefault.objects.filter(id__in=default_ids).delete()

    defaults = list(MealSlotDefault.objects.all())
    if not any(_norm(row.name) in LUNCH_NAMES for row in defaults):
        MealSlotDefault.objects.create(name='Lunch', order=0)
    defaults = list(MealSlotDefault.objects.all())
    if not any(_norm(row.name) in DINNER_NAMES for row in defaults):
        MealSlotDefault.objects.create(name='Dinner', order=1)

    lunch_name = next(
        (row.name for row in MealSlotDefault.objects.all() if _norm(row.name) in LUNCH_NAMES),
        'Lunch',
    )
    dinner_name = next(
        (row.name for row in MealSlotDefault.objects.all() if _norm(row.name) in DINNER_NAMES),
        'Dinner',
    )

    for user in User.objects.all():
        slots = list(MealSlot.objects.filter(user=user))
        if not any(_norm(slot.name) in LUNCH_NAMES for slot in slots):
            MealSlot.objects.create(user=user, name=lunch_name, order=100)
        slots = list(MealSlot.objects.filter(user=user))
        if not any(_norm(slot.name) in DINNER_NAMES for slot in slots):
            MealSlot.objects.create(user=user, name=dinner_name, order=101)
        slots = list(MealSlot.objects.filter(user=user).order_by('order', 'id'))
        for i, slot in enumerate(slots):
            slot.order = 200 + i
            slot.save(update_fields=['order'])
        slots = list(MealSlot.objects.filter(user=user).order_by('order', 'id'))
        for i, slot in enumerate(slots):
            slot.order = i
            slot.save(update_fields=['order'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_alter_help_texts_and_choices'),
    ]

    operations = [
        migrations.RunPython(remove_breakfast, migrations.RunPython.noop),
    ]

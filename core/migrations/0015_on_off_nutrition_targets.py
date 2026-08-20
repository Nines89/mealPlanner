from decimal import Decimal, ROUND_HALF_UP

import django.db.models.deletion
from django.db import migrations, models


def midpoint_grams(kcal, pct_min, pct_max, kcal_per_gram):
    mid = (Decimal(pct_min) + Decimal(pct_max)) / Decimal('2') / Decimal('100')
    grams = Decimal(kcal) * mid / Decimal(kcal_per_gram)
    return int(grams.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def seed_on_off_targets(apps, schema_editor):
    NutritionTarget = apps.get_model('core', 'NutritionTarget')
    MealSlotTarget = apps.get_model('core', 'MealSlotTarget')
    UserProfile = apps.get_model('core', 'UserProfile')
    WeekPlan = apps.get_model('core', 'WeekPlan')

    specs = (
        ('on', 'ON', 1700),
        ('off', 'OFF', 1500),
    )
    keep_ids = []
    for kind, name, kcal in specs:
        nt, _created = NutritionTarget.objects.update_or_create(
            kind=kind,
            defaults={
                'name': name,
                'owner': None,
                'is_system': True,
                'target_kcal': kcal,
                'diet_style': 'none',
                'target_protein': midpoint_grams(kcal, 15, 25, 4),
                'target_carbs': midpoint_grams(kcal, 45, 50, 4),
                'target_fat': midpoint_grams(kcal, 20, 25, 9),
                'protein_pct_min': 15,
                'protein_pct_max': 25,
                'carbs_pct_min': 45,
                'carbs_pct_max': 50,
                'fat_pct_min': 20,
                'fat_pct_max': 25,
            },
        )
        keep_ids.append(nt.id)

    others = NutritionTarget.objects.exclude(id__in=keep_ids)
    WeekPlan.objects.filter(nutrition_target__in=others).update(nutrition_target=None)
    UserProfile.objects.filter(nutrition_target__in=others).update(nutrition_target=None)
    MealSlotTarget.objects.filter(nutrition_target__in=others).delete()
    others.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_lunch_dinner_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='nutritiontarget',
            name='kind',
            field=models.CharField(
                blank=True,
                choices=[('on', 'ON'), ('off', 'OFF')],
                help_text='ON or OFF day. Only these two targets are used.',
                max_length=8,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='nutritiontarget',
            name='protein_pct_min',
            field=models.PositiveSmallIntegerField(default=15),
        ),
        migrations.AddField(
            model_name='nutritiontarget',
            name='protein_pct_max',
            field=models.PositiveSmallIntegerField(default=25),
        ),
        migrations.AddField(
            model_name='nutritiontarget',
            name='carbs_pct_min',
            field=models.PositiveSmallIntegerField(default=45),
        ),
        migrations.AddField(
            model_name='nutritiontarget',
            name='carbs_pct_max',
            field=models.PositiveSmallIntegerField(default=50),
        ),
        migrations.AddField(
            model_name='nutritiontarget',
            name='fat_pct_min',
            field=models.PositiveSmallIntegerField(default=20),
        ),
        migrations.AddField(
            model_name='nutritiontarget',
            name='fat_pct_max',
            field=models.PositiveSmallIntegerField(default=25),
        ),
        migrations.AlterField(
            model_name='nutritiontarget',
            name='name',
            field=models.CharField(help_text='ON or OFF', max_length=100),
        ),
        migrations.AlterField(
            model_name='nutritiontarget',
            name='target_protein',
            field=models.PositiveIntegerField(
                default=150,
                help_text='grams (midpoint of the protein % range)',
            ),
        ),
        migrations.AlterField(
            model_name='nutritiontarget',
            name='target_carbs',
            field=models.PositiveIntegerField(
                default=200,
                help_text='grams (midpoint of the carb % range)',
            ),
        ),
        migrations.AlterField(
            model_name='nutritiontarget',
            name='target_fat',
            field=models.PositiveIntegerField(
                default=70,
                help_text='grams (midpoint of the fat % range)',
            ),
        ),
        migrations.AlterField(
            model_name='weekplan',
            name='nutrition_target',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='week_plans',
                to='core.nutritiontarget',
            ),
        ),
        migrations.AddField(
            model_name='weekplandaykind',
            name='kind',
            field=models.CharField(
                choices=[('on', 'ON'), ('off', 'OFF')],
                default='off',
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name='weekplandaykind',
            name='day_profile',
            field=models.ForeignKey(
                blank=True,
                help_text='Unused; kept for old rows.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='week_plan_day_assignments',
                to='core.dayprofile',
            ),
        ),
        migrations.RunPython(seed_on_off_targets, migrations.RunPython.noop),
    ]

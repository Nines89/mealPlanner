# Generated manually: created_at su NutritionTarget + vincolo WeekPlan (owner, week_start)

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_mealslottarget'),
    ]

    operations = [
        migrations.AddField(
            model_name='nutritiontarget',
            name='created_at',
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                editable=False,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='nutritiontarget',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, editable=False),
        ),
        migrations.AddConstraint(
            model_name='weekplan',
            constraint=models.UniqueConstraint(
                condition=models.Q(owner__isnull=False, week_start__isnull=False),
                fields=('owner', 'week_start'),
                name='core_weekplan_owner_week_start_uniq',
            ),
        ),
    ]

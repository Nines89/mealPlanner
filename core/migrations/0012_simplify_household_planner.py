import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def copy_active_targets(apps, schema_editor):
    UserProfile = apps.get_model('core', 'UserProfile')
    HouseholdMember = apps.get_model('core', 'HouseholdMember')
    NutritionTarget = apps.get_model('core', 'NutritionTarget')

    for profile in UserProfile.objects.all():
        member = (
            HouseholdMember.objects.filter(
                household__owner_id=profile.user_id,
                nutrition_target_id__isnull=False,
            )
            .order_by('sort_order', 'id')
            .first()
        )
        if member:
            profile.nutrition_target_id = member.nutrition_target_id
            profile.save(update_fields=['nutrition_target'])
            continue
        nt = (
            NutritionTarget.objects.filter(owner_id=profile.user_id, is_system=False)
            .order_by('-created_at')
            .first()
        )
        if nt:
            profile.nutrition_target_id = nt.id
            profile.save(update_fields=['nutrition_target'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_dayprofilemembermodifier'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='nutrition_target',
            field=models.ForeignKey(
                blank=True,
                help_text='Active household nutrition target (one plate, one target).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='active_for_profiles',
                to='core.nutritiontarget',
            ),
        ),
        migrations.RunPython(copy_active_targets, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='householdmember',
            name='linked_user',
        ),
        migrations.RemoveField(
            model_name='householdmember',
            name='nutrition_target',
        ),
        migrations.AlterField(
            model_name='mealingredient',
            name='grams',
            field=models.DecimalField(
                decimal_places=1,
                help_text='Grams on the shared plate (same for every household member).',
                max_digits=6,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.DeleteModel(
            name='DayProfileMemberModifier',
        ),
        migrations.DeleteModel(
            name='MealIngredientMemberPortion',
        ),
        migrations.DeleteModel(
            name='WeekPlanSlotAttendance',
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


GENRE_CHOICES = [
    ('pasta_cereali', 'Pasta / Cereali'),
    ('pollo_tacchino', 'Pollo / Tacchino'),
    ('pesce', 'Pesce'),
    ('carni_rosse', 'Carni rosse'),
    ('insaccati', 'Insaccati'),
    ('uova', 'Uova'),
    ('legumi', 'Legumi'),
    ('verdura', 'Verdura'),
    ('formaggio', 'Formaggio'),
    ('zuppe', 'Zuppe'),
    ('insalate', 'Insalate'),
    ('piadine', 'Piadine'),
]


def copy_meal_genre_onto_slots(apps, schema_editor):
    WeekPlanSlot = apps.get_model('core', 'WeekPlanSlot')
    for slot in WeekPlanSlot.objects.select_related('meal').iterator():
        meal_genre = slot.meal.genre if slot.meal_id else ''
        if meal_genre and slot.genre != meal_genre:
            slot.genre = meal_genre
            slot.save(update_fields=['genre'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_meal_genre'),
    ]

    operations = [
        migrations.AddField(
            model_name='weekplanslot',
            name='genre',
            field=models.CharField(
                blank=True,
                choices=GENRE_CHOICES,
                default='',
                help_text='Recipe category chosen first (Soups, Fish, …).',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='weekplanslot',
            name='meal',
            field=models.ForeignKey(
                blank=True,
                help_text='Specific dish; optional until a recipe is chosen or Fill runs.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='slots',
                to='core.meal',
            ),
        ),
        migrations.RunPython(copy_meal_genre_onto_slots, migrations.RunPython.noop),
    ]

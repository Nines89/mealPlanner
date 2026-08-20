from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_on_off_nutrition_targets'),
    ]

    operations = [
        migrations.AddField(
            model_name='meal',
            name='genre',
            field=models.CharField(
                blank=True,
                choices=[
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
                ],
                default='',
                help_text='Household recipe group (Pasta / Pollo / Pesce / …).',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='meal',
            name='name',
            field=models.CharField(max_length=120),
        ),
    ]

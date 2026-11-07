from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_shoppinglistmanualitem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShoppingListHiddenIngredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateField()),
                ('ingredient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.ingredient')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shopping_list_hidden_ingredients', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(fields=('owner', 'week_start', 'ingredient'), name='core_shoppinglisthidden_owner_week_ingredient_uniq'),
                ],
            },
        ),
    ]

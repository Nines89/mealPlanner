from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_shoppinglistorder'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShoppingListManualItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateField()),
                ('name', models.CharField(max_length=100)),
                ('quantity', models.CharField(blank=True, max_length=40)),
                ('section', models.CharField(max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shopping_list_manual_items', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at', 'id'],
            },
        ),
    ]

from django.db import migrations


LEGUME_PROTEIN_NAMES = (
    'Ceci secchi',
    'Ceci in scatola',
    'Lenticchie secche',
    'Lenticchie in scatola',
)


def reclassify_legume_proteins(apps, schema_editor):
    Ingredient = apps.get_model('core', 'Ingredient')
    Ingredient.objects.filter(name__in=LEGUME_PROTEIN_NAMES).update(
        category='protein',
        vegetable_subcategory='',
    )


class Migration(migrations.Migration):
    dependencies = [('core', '0018_alter_dayprofile_notes_alter_ingredient_category_and_more')]

    operations = [migrations.RunPython(reclassify_legume_proteins, migrations.RunPython.noop)]

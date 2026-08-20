from django.core.management.base import BaseCommand

from core.catalog import seed_catalog


class Command(BaseCommand):
    help = (
        'Upsert system ingredients from core/data/ingredients.csv and rebuild '
        'complete meals grouped by genre. Add CSV rows and recipes, then re-run.'
    )

    def handle(self, *args, **options):
        stats = seed_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                'Catalog ready: '
                f'{stats["ingredients"]} ingredients '
                f'({stats["created_ingredients"]} new), '
                f'{stats["system_meals"]} system meals '
                f'({stats["created_meals"]} new, {stats["deleted_meals"]} removed).'
            )
        )

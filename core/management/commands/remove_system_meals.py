from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Meal


class Command(BaseCommand):
    help = 'Rimuove i piatti "di sistema" (da recipes.py). Dry-run di default; --apply per eliminare.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='elimina davvero')

    def handle(self, *args, **options):
        system = list(Meal.objects.filter(is_system=True))
        used = [meal for meal in system if meal.slots.exists()]
        removable = [meal for meal in system if not meal.slots.exists()]
        self.stdout.write(
            f'Piatti di sistema: {len(system)} — eliminabili: {len(removable)}, '
            f'usati in un piano (da lasciare): {len(used)}'
        )
        for meal in used:
            self.stdout.write(f'  [USATO] {meal.name}')
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Dry-run: nessuna modifica. Usa --apply.'))
            return
        with transaction.atomic():
            for meal in removable:
                meal.delete()
        self.stdout.write(self.style.SUCCESS(f'Eliminati {len(removable)} piatti di sistema.'))

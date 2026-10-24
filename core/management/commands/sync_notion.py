from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.notion_sync import apply_plan, build_plan, fetch_notion_recipes, prepare_payload


class Command(BaseCommand):
    help = 'Confronta le ricette Notion con il DB (dry-run). Con --apply scrive.'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='username proprietario (default: primo utente)')
        parser.add_argument('--apply', action='store_true', help='applica le modifiche')
        parser.add_argument('--prune', action='store_true', help='rimuove le ricette sparite da Notion')

    def handle(self, *args, **options):
        owner = self._owner(options['user'])
        try:
            payload = prepare_payload(fetch_notion_recipes())
        except NotImplementedError as exc:
            raise CommandError(str(exc)) from exc
        plan = build_plan(owner, payload)
        self._report(plan)
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Dry-run: nessuna modifica. Usa --apply.'))
            return
        result = apply_plan(plan, owner, prune=options['prune'])
        self.stdout.write(self.style.SUCCESS(
            f'create={result.created} aggiornate={result.updated} invariate={result.unchanged} '
            f'errori={result.errors} rimosse={result.pruned} non_rimosse={result.prune_skipped}'
        ))

    def _owner(self, username):
        queryset = User.objects.all()
        owner = queryset.filter(username=username).first() if username else queryset.order_by('id').first()
        if owner is None:
            raise CommandError('Utente non trovato.')
        return owner

    def _report(self, plan):
        for action in plan.actions:
            if action.status == 'unchanged':
                continue
            self.stdout.write(f'[{action.status.upper():6}] {action.name}')
            for line in (*action.changes, *action.warnings, *action.errors):
                self.stdout.write(f'         {line}')
        for meal in plan.orphans:
            self.stdout.write(f'[ORPHAN] {meal.name}')
        self.stdout.write(
            f'Totale: {len(plan.new)} nuove, {len(plan.updates)} modificate, '
            f'{len(plan.unchanged)} invariate, {len(plan.errors)} errori, '
            f'{len(plan.orphans)} orfane.'
        )
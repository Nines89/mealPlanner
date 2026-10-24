"""
Sync ricette Notion → Meal (owner=utente, is_system=False, source='notion').

Flusso in due fasi:
1. ``prepare_payload(fetch_notion_recipes())`` + ``build_plan(owner, payload)``
   confronta con il DB e NON scrive nulla (anteprima / dry-run).
2. ``apply_plan(plan, owner)`` scrive, in transazione, solo new/update.

Contratto dati: vedi ``fetch_notion_recipes``.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .catalog import default_grams_for, ensure_staple_carb
from .models import Ingredient, Meal, MealGenre, MealIngredient
from .planning import GENERATED_MEAL_MARKER, quantize_grams
from .recipes import INGREDIENT_ALIASES

SOURCE = 'notion'
MEAL_NAME_MAX = 120

NEW, UPDATE, UNCHANGED, ERROR = 'new', 'update', 'unchanged', 'error'


# ─────────────────────────────────────────
# DA IMPLEMENTARE (lato Notion)
# ─────────────────────────────────────────

def fetch_notion_recipes():
    """
    TODO: leggere TUTTE le ricette da Notion e restituire una lista di dict.

    Un dict per ricetta:

        {
            'external_id': str,   # ID pagina Notion. Stabile, univoco, obbligatorio.
            'name':        str,   # titolo ricetta, obbligatorio
            'genre':       str,   # valore MealGenre ('pasta_cereali') oppure
                                  # label ('Pasta / Cereali'); case-insensitive
            'ingredients': [      # almeno 1 elemento
                {'name': 'Pasta di semola', 'grams': 80},    # grams: numero, str o None
                {'name': 'zucchina',        'grams': 200},
                {'name': 'ricotta',         'grams': None},  # None → default di catalog.py
            ],
        }

    Note:
    - ``ingredients`` può essere anche una stringa nel formato di recipes.py
      (``'pasta, zucchina 200, ricotta'``): viene parsata qui.
    - ``name`` ingrediente: nome esatto del catalogo (``Ingredient.name``) oppure
      alias di ``recipes.INGREDIENT_ALIASES``. Confronto case-insensitive.
    - Niente I/O Django qui dentro e niente scritture: solo lettura da Notion.
    - Eccezioni (rete, auth, 403 se l'integrazione non è condivisa col database)
      vanno lasciate propagare: view e command le gestiscono.
    """
    raise NotImplementedError('Implementare fetch_notion_recipes() con la libreria Notion.')


# ─────────────────────────────────────────
# NORMALIZZAZIONE (contratto → dati puliti, JSON-safe)
# ─────────────────────────────────────────

class RecipeFormatError(ValueError):
    pass


_GENRE_LOOKUP = {}
for _value, _label in MealGenre.choices:
    _GENRE_LOOKUP[_value.lower()] = _value
    _GENRE_LOOKUP[str(_label).lower()] = _value


def _peek(raw, key):
    return str(raw.get(key) or '').strip() if isinstance(raw, dict) else ''


def _normalize_grams(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        grams = Decimal(str(value).strip().replace(',', '.'))
    except InvalidOperation as exc:
        raise RecipeFormatError(f'grammi non numerici: {value!r}') from exc
    if grams <= 0:
        raise RecipeFormatError(f'grammi non positivi: {value!r}')
    return str(grams)


def _split_ingredient_string(part):
    part = part.strip()
    bits = part.rsplit(' ', 1)
    if len(bits) == 2 and bits[1].replace('.', '', 1).replace(',', '', 1).isdigit():
        return bits[0].strip(), bits[1]
    return part, None


def _normalize_ingredients(value):
    if isinstance(value, str):
        value = [_split_ingredient_string(p) for p in value.split(',') if p.strip()]
    result = []
    for entry in value or []:
        if isinstance(entry, dict):
            name, grams = entry.get('name'), entry.get('grams')
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            name, grams = entry
        else:
            raise RecipeFormatError(f'ingrediente in formato non valido: {entry!r}')
        name = str(name or '').strip()
        if not name:
            raise RecipeFormatError('ingrediente senza nome')
        result.append({'name': name, 'grams': _normalize_grams(grams)})
    return result


def normalize_recipe(raw):
    if not isinstance(raw, dict):
        raise RecipeFormatError('record non valido (atteso dict)')
    external_id = _peek(raw, 'external_id')
    name = _peek(raw, 'name')
    if not external_id:
        raise RecipeFormatError('external_id mancante')
    if not name:
        raise RecipeFormatError('name mancante')
    genre = _GENRE_LOOKUP.get(_peek(raw, 'genre').lower())
    if genre is None:
        raise RecipeFormatError(f'categoria sconosciuta: {raw.get("genre")!r}')
    ingredients = _normalize_ingredients(raw.get('ingredients'))
    if not ingredients:
        raise RecipeFormatError('nessun ingrediente')
    return {
        'external_id': external_id,
        'name': name,
        'genre': genre,
        'ingredients': ingredients,
    }


def prepare_payload(raw_recipes):
    """
    Normalizza l'output di ``fetch_notion_recipes``. Il risultato è JSON-safe
    (la view lo tiene in sessione tra anteprima e applicazione).
    """
    recipes, rejected, known_ids = [], [], []
    for raw in raw_recipes:
        external_id = _peek(raw, 'external_id')
        if external_id:
            known_ids.append(external_id)
        try:
            recipes.append(normalize_recipe(raw))
        except RecipeFormatError as exc:
            rejected.append(
                {'external_id': external_id, 'name': _peek(raw, 'name'), 'error': str(exc)}
            )
    return {'recipes': recipes, 'rejected': rejected, 'known_ids': known_ids}


# ─────────────────────────────────────────
# PIANO (confronto con il DB, nessuna scrittura)
# ─────────────────────────────────────────

@dataclass
class RecipeAction:
    external_id: str
    name: str
    status: str
    genre: str = ''
    items: list = field(default_factory=list)      # [(Ingredient, Decimal)]
    meal: object = None                             # Meal esistente, se c'è
    changes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)


@dataclass
class SyncPlan:
    actions: list
    orphans: list   # Meal source='notion' non più presenti su Notion

    def _with(self, status):
        return [a for a in self.actions if a.status == status]

    @property
    def new(self):
        return self._with(NEW)

    @property
    def updates(self):
        return self._with(UPDATE)

    @property
    def unchanged(self):
        return self._with(UNCHANGED)

    @property
    def errors(self):
        return self._with(ERROR)

    @property
    def has_changes(self):
        return bool(self.new or self.updates)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    pruned: int = 0
    prune_skipped: int = 0


class _CatalogIndex:
    def __init__(self):
        self.by_name = {ing.name: ing for ing in Ingredient.objects.all()}
        self.by_lower = {name.lower(): ing for name, ing in self.by_name.items()}

    def resolve(self, name):
        key = name.strip().lower()
        ingredient = self.by_lower.get(key)
        if ingredient is None:
            alias = INGREDIENT_ALIASES.get(key)
            if alias:
                ingredient = self.by_name.get(alias)
        return ingredient


class _OwnerMeals:
    def __init__(self, owner):
        queryset = (
            Meal.objects.filter(owner=owner, is_system=False)
            .exclude(description=GENERATED_MEAL_MARKER)
            .prefetch_related('meal_ingredients__ingredient')
        )
        self.all = list(queryset)
        self.by_external = {m.external_id: m for m in self.all if m.external_id}
        self.unlinked_by_name = {}
        for meal in self.all:
            if not meal.external_id:
                self.unlinked_by_name.setdefault(meal.name.lower(), meal)
        self.system_names = {
            name.lower()
            for name in Meal.objects.filter(is_system=True).values_list('name', flat=True)
        }

    def orphans(self, incoming_ids):
        return [
            m for m in self.all
            if m.source == SOURCE and m.external_id not in incoming_ids
        ]


def _resolve_items(recipe, catalog, action):
    resolved, seen, unknown = [], set(), []
    for entry in recipe['ingredients']:
        ingredient = catalog.resolve(entry['name'])
        if ingredient is None:
            unknown.append(entry['name'])
            continue
        if ingredient.id in seen:
            action.warnings.append(f'ingrediente duplicato ignorato: {ingredient.name}')
            continue
        seen.add(ingredient.id)
        grams = Decimal(entry['grams']) if entry['grams'] else default_grams_for(ingredient)
        resolved.append((ingredient, grams))
    if unknown:
        action.errors.append('ingredienti non in catalogo: ' + ', '.join(unknown))
        return
    try:
        with_carb = ensure_staple_carb(
            recipe['genre'], recipe['name'], resolved, catalog.by_name
        )
    except ValueError as exc:
        action.errors.append(str(exc))
        return
    if len(with_carb) > len(resolved):
        action.warnings.append(f'carboidrato di base aggiunto: {with_carb[-1][0].name}')
    action.items = [(ing, quantize_grams(grams)) for ing, grams in with_carb]


def _diff(meal, action):
    changes = []
    if meal.name != action.name:
        changes.append(f'nome: {meal.name} → {action.name}')
    if meal.genre != action.genre:
        changes.append(f'categoria: {meal.genre or "—"} → {action.genre}')
    old = {r.ingredient_id: (r.ingredient.name, r.grams) for r in meal.meal_ingredients.all()}
    new = {ing.id: (ing.name, grams) for ing, grams in action.items}
    for ing_id, (name, grams) in new.items():
        if ing_id not in old:
            changes.append(f'+ {name} {grams:.0f} g')
        elif old[ing_id][1] != grams:
            changes.append(f'{name}: {old[ing_id][1]:.0f} → {grams:.0f} g')
    for ing_id, (name, _grams) in old.items():
        if ing_id not in new:
            changes.append(f'− {name}')
    return changes


def _plan_recipe(recipe, catalog, existing, claimed):
    action = RecipeAction(
        external_id=recipe['external_id'],
        name=recipe['name'][:MEAL_NAME_MAX],
        genre=recipe['genre'],
        status=ERROR,
    )
    _resolve_items(recipe, catalog, action)
    if action.errors:
        return action

    meal = existing.by_external.get(action.external_id)
    if meal is None:
        candidate = existing.unlinked_by_name.get(action.name.lower())
        if candidate is not None and candidate.id not in claimed:
            meal = candidate
            action.warnings.append('collegata a una ricetta esistente con lo stesso nome')
    if meal is None:
        action.status = NEW
        if action.name.lower() in existing.system_names:
            action.warnings.append(
                'stesso nome di un piatto di sistema: comparirà due volte nel pool'
            )
        return action

    claimed.add(meal.id)
    action.meal = meal
    action.changes = _diff(meal, action)
    needs_link = meal.external_id != action.external_id
    action.status = UPDATE if (action.changes or needs_link) else UNCHANGED
    return action


def build_plan(owner, payload):
    """Confronta il payload con il DB. Sola lettura."""
    catalog = _CatalogIndex()
    existing = _OwnerMeals(owner)
    actions = [
        RecipeAction(
            external_id=rej['external_id'],
            name=rej['name'] or '(senza nome)',
            status=ERROR,
            errors=[rej['error']],
        )
        for rej in payload.get('rejected', [])
    ]
    seen, claimed = set(), set()
    for recipe in payload.get('recipes', []):
        if recipe['external_id'] in seen:
            actions.append(
                RecipeAction(
                    external_id=recipe['external_id'],
                    name=recipe['name'],
                    status=ERROR,
                    errors=['external_id duplicato nell\'input'],
                )
            )
            continue
        seen.add(recipe['external_id'])
        actions.append(_plan_recipe(recipe, catalog, existing, claimed))
    known = set(payload.get('known_ids', [])) | seen
    return SyncPlan(actions=actions, orphans=existing.orphans(known))


# ─────────────────────────────────────────
# APPLICAZIONE (scrive)
# ─────────────────────────────────────────

def _write_items(meal, items):
    meal.meal_ingredients.all().delete()
    MealIngredient.objects.bulk_create(
        [MealIngredient(meal=meal, ingredient=ing, grams=grams) for ing, grams in items]
    )


@transaction.atomic
def apply_plan(plan, owner, prune=False):
    """
    Applica new/update; gli errori restano fuori. ``plan`` deve essere fresco
    (costruito nella stessa richiesta): le view lo ricalcolano prima di applicare.

    ``prune``: elimina i Meal 'notion' spariti da Notion, solo se non usati in
    nessun piano (WeekPlanSlot.meal è PROTECT). Ignorato se l'input è vuoto, per
    non svuotare il catalogo in caso di lettura Notion fallita.
    """
    now = timezone.now()
    result = SyncResult()
    for action in plan.actions:
        if action.status == NEW:
            meal = Meal.objects.create(
                owner=owner,
                is_system=False,
                name=action.name,
                genre=action.genre,
                description='',
                external_id=action.external_id,
                source=SOURCE,
                synced_at=now,
            )
            _write_items(meal, action.items)
            result.created += 1
        elif action.status == UPDATE:
            meal = action.meal
            meal.name = action.name
            meal.genre = action.genre
            meal.external_id = action.external_id
            meal.source = SOURCE
            meal.synced_at = now
            meal.save(update_fields=['name', 'genre', 'external_id', 'source', 'synced_at'])
            _write_items(meal, action.items)
            result.updated += 1
        elif action.status == UNCHANGED:
            result.unchanged += 1
        else:
            result.errors += 1
    if prune and plan.actions:
        for meal in plan.orphans:
            if meal.slots.exists():
                result.prune_skipped += 1
                continue
            meal.delete()
            result.pruned += 1
    return result
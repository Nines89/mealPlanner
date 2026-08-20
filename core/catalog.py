"""
System ingredient + meal catalog.

Ingredients live in ``core/data/ingredients.csv`` (Italian names, values per 100 g).
Dishes live in ``core/recipes.py``, grouped by genre. Add rows / recipes, then run:
python manage.py seed_catalog
"""
import csv
from decimal import Decimal
from pathlib import Path

from .models import (
    Ingredient,
    IngredientCategory,
    Meal,
    MealIngredient,
    SeasonEntry,
    Tag,
    TagType,
    VegetableSubcategory,
    WeekPlanSlot,
)
from .planning import quantize_grams
from .recipes import INGREDIENT_ALIASES, RECIPE_NAMES, RECIPES

ALL_YEAR = ('spring', 'summer', 'autumn', 'winter')
VEGAN = ('vegan', 'vegano', 'vegetarian', 'vegetariano')
VEGETARIAN = ('vegetarian', 'vegetariano')
INGREDIENTS_CSV = Path(__file__).resolve().parent / 'data' / 'ingredients.csv'
TAG_GROUPS = {
    'vegan': VEGAN,
    'vegetarian': VEGETARIAN,
    'fish': ('fish', 'Pesce'),
    'egg': ('egg', 'Uova'),
    'gluten': ('gluten', 'glutine'),
    'lactose': ('lactose', 'lattosio'),
    'nuts': ('nuts', 'Frutta a guscio'),
}

# English leftovers → Italian names (user-facing catalog).
INGREDIENT_RENAMES = {
    'Chicken breast': 'Petto di pollo',
    'Chicken thigh': 'Coscia di pollo',
    'Turkey breast': 'Petto di tacchino',
    'Turkey mince': 'Macinato di tacchino',
    'Lean beef': 'Manzo magro',
    'Beef mince': 'Macinato di manzo',
    'Pork loin': 'Lonza di maiale',
    'Pork mince': 'Macinato di maiale',
    'Veal': 'Vitello',
    'Rabbit': 'Coniglio',
    'Cooked ham': 'Prosciutto cotto',
    'Whole eggs': 'Uova intere',
    'Egg whites': 'Albumi',
    'Salmon': 'Salmone',
    'Cod': 'Merluzzo',
    'Sea bass': 'Spigola',
    'Sea bream': 'Orata',
    'Trout': 'Trota',
    'Canned tuna in water': 'Tonno al naturale',
    'Canned tuna in oil': "Tonno all'olio",
    'Mackerel': 'Sgombro',
    'Sardines': 'Sardine',
    'Shrimp': 'Gamberi',
    'Mussels': 'Cozze',
    'Squid': 'Calamari',
    'Cottage cheese': 'Fiocchi di latte',
    'Greek yogurt 0%': 'Yogurt greco 0%',
    'Spinach': 'Spinaci',
    'Zucchini': 'Zucchine',
    'Cauliflower': 'Cavolfiore',
    'Tomato': 'Pomodoro',
    'Cherry tomato': 'Pomodorini',
    'Bell pepper': 'Peperone',
    'Carrot': 'Carota',
    'Green beans': 'Fagiolini',
    'Cucumber': 'Cetriolo',
    'Lettuce': 'Lattuga',
    'Rocket': 'Rucola',
    'Kale': 'Cavolo riccio',
    'Savoy cabbage': 'Verza',
    'Red cabbage': 'Cavolo rosso',
    'Eggplant': 'Melanzana',
    'White mushrooms': 'Funghi champignon',
    'Onion': 'Cipolla',
    'Garlic': 'Aglio',
    'Leek': 'Porro',
    'Fennel': 'Finocchio',
    'Celery': 'Sedano',
    'Asparagus': 'Asparagi',
    'Artichoke': 'Carciofo',
    'Pumpkin': 'Zucca',
    'Beetroot': 'Barbabietola',
    'Peas': 'Piselli',
    'Sweetcorn': 'Mais',
    'Brussels sprouts': 'Cavoletti di Bruxelles',
    'Swiss chard': 'Bietole',
    'Dried lentils': 'Lenticchie secche',
    'Canned lentils': 'Lenticchie in scatola',
    'Dried chickpeas': 'Ceci secchi',
    'Canned chickpeas': 'Ceci in scatola',
    'Dried white beans': 'Fagioli cannellini secchi',
    'Canned white beans': 'Fagioli cannellini in scatola',
    'Basmati rice': 'Riso basmati',
    'Brown rice': 'Riso integrale',
    'Arborio rice': 'Riso arborio',
    'Semolina pasta': 'Pasta di semola',
    'Whole wheat pasta': 'Pasta integrale',
    'Potato': 'Patata',
    'Sweet potato': 'Patata dolce',
    'Pearl barley': 'Orzo perlato',
    'Rolled oats': "Fiocchi d'avena",
    'White bread': 'Pane bianco',
    'Whole wheat bread': 'Pane integrale',
    'Olive oil': "Olio d'oliva",
    'Sunflower oil': 'Olio di semi di girasole',
    'Butter': 'Burro',
    'Coconut oil': 'Olio di cocco',
    'Green olives': 'Olive verdi',
    'Almonds': 'Mandorle',
    'Walnuts': 'Noci',
    'Peanuts': 'Arachidi',
    'Peanut butter': 'Burro di arachidi',
    'Tahini': 'Tahina',
    'Semi-skimmed milk': 'Latte parzialmente scremato',
    'Parmesan': 'Parmigiano',
    'Apple': 'Mela',
    'Orange': 'Arancia',
    'Lemon': 'Limone',
    'Strawberry': 'Fragola',
    'Pear': 'Pera',
    'Blueberries': 'Mirtilli',
}

SYSTEM_MEAL_RENAMES = {
    'Pollo con verdure': 'Pollo, zucchine e riso',
    'Chicken, zucchini and rice': 'Pollo, zucchine e riso',
    'Chicken, broccoli and pasta': 'Pollo, broccoli e pasta',
    'Turkey, peppers and rice': 'Tacchino, peperoni e riso',
    'Beef, tomato and pasta': 'Manzo, pomodoro e pasta',
    'Salmon, spinach and rice': 'Salmone, spinaci e riso',
    'Cod, zucchini and potato': 'Merluzzo, zucchine e patate',
    'Tuna, green beans and rice': 'Tonno, fagiolini e riso',
    'Eggs, spinach and potato': 'Uova, spinaci e patate',
    'Tofu, broccoli and rice': 'Tofu, broccoli e riso',
}

TAGS = (
    ('vegan', TagType.DIET),
    ('vegetarian', TagType.DIET),
    ('vegano', TagType.DIET),
    ('vegetariano', TagType.DIET),
    ('gluten', TagType.ALLERGEN),
    ('glutine', TagType.ALLERGEN),
    ('lactose', TagType.ALLERGEN),
    ('lattosio', TagType.ALLERGEN),
    ('fish', TagType.ALLERGEN),
    ('Pesce', TagType.ALLERGEN),
    ('egg', TagType.ALLERGEN),
    ('Uova', TagType.ALLERGEN),
    ('nuts', TagType.ALLERGEN),
    ('Frutta a guscio', TagType.ALLERGEN),
)

# Nutrition per 100 g is in core/data/ingredients.csv (dry carbs, raw proteins/veg, oil as-is).


# Dishes: core/recipes.py
SYSTEM_MEALS = RECIPE_NAMES

_CATEGORIES = {choice.value for choice in IngredientCategory}
_VEG_SUBCATEGORIES = {choice.value for choice in VegetableSubcategory}
_MACRO_FIELDS = ('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sugars', 'saturated_fat', 'salt')


def _expand_tags(raw):
    names = []
    for part in (raw or '').split(','):
        key = part.strip()
        if not key:
            continue
        names.extend(TAG_GROUPS.get(key, (key,)))
    return tuple(dict.fromkeys(names))


def _parse_seasons(raw):
    text = (raw or '').strip().lower()
    if not text or text == 'all':
        return ALL_YEAR
    return tuple(part.strip() for part in text.split(',') if part.strip())


def load_ingredient_specs(path=None):
    """Parse the ingredients CSV. Values are per 100 g."""
    csv_path = Path(path or INGREDIENTS_CSV)
    specs = []
    seen = set()
    with csv_path.open(encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            spec = _ingredient_spec_from_row(row, seen)
            if spec is not None:
                specs.append(spec)
    return specs


def _ingredient_spec_from_row(row, seen):
    name = (row.get('name') or '').strip()
    if not name:
        return None
    if name in seen:
        raise ValueError(f'Duplicate ingredient name in CSV: {name}')
    seen.add(name)
    category = (row.get('category') or '').strip()
    if category not in _CATEGORIES:
        raise ValueError(f'Unknown category for {name!r}: {category!r}')
    spec = {
        'name': name,
        'category': category,
        'vegetable_subcategory': _vegetable_subcategory(name, category, row),
        'tags': _expand_tags(row.get('tags') or ''),
        'seasons': _parse_seasons(row.get('seasons') or ''),
    }
    for field in _MACRO_FIELDS:
        spec[field] = (row.get(field) or '0').strip() or '0'
    return spec


def _vegetable_subcategory(name, category, row):
    subcategory = (row.get('subcategory') or '').strip()
    if category != IngredientCategory.VEGETABLE:
        return ''
    if subcategory and subcategory not in _VEG_SUBCATEGORIES:
        raise ValueError(
            f'Unknown vegetable subcategory for {name!r}: {subcategory!r}'
        )
    return subcategory


def parse_recipe_items(spec):
    items = []
    for raw in spec.split(','):
        part = raw.strip()
        if not part:
            continue
        key = part.lower()
        grams = None
        if key not in INGREDIENT_ALIASES:
            bits = part.rsplit(' ', 1)
            if len(bits) == 2 and bits[1].isdigit():
                maybe = bits[0].strip().lower()
                if maybe in INGREDIENT_ALIASES:
                    key = maybe
                    grams = Decimal(bits[1])
        items.append((key, grams))
    return items


_DEFAULT_GRAMS_BY_NAME = {
    'burro': Decimal('10'),
    'aglio': Decimal('5'),
    'peperoncino': Decimal('3'),
    'curry': Decimal('3'),
    'prezzemolo': Decimal('5'),
    'salvia': Decimal('5'),
    'erba cipollina': Decimal('5'),
    'limone': Decimal('20'),
    'parmigiano': Decimal('20'),
    'pecorino': Decimal('20'),
    'formaggio stagionato': Decimal('20'),
    'pesto': Decimal('45'),
    'pangrattato': Decimal('20'),
    'farina': Decimal('20'),
    'noci': Decimal('15'),
    'mandorle': Decimal('15'),
    'anacardi': Decimal('15'),
    'pinoli': Decimal('15'),
    'semi misti': Decimal('15'),
    'capperi': Decimal('10'),
    'aceto': Decimal('10'),
    'salsa di soia': Decimal('10'),
    'senape': Decimal('10'),
    'miele': Decimal('10'),
    'ketchup': Decimal('20'),
}
_DEFAULT_GRAMS_BY_CATEGORY = {
    IngredientCategory.PROTEIN: Decimal('150'),
    IngredientCategory.CARB: Decimal('80'),
    IngredientCategory.VEGETABLE: Decimal('150'),
    IngredientCategory.FAT: Decimal('15'),
    IngredientCategory.DAIRY: Decimal('40'),
    IngredientCategory.FRUIT: Decimal('100'),
}
_OIL_GRAMS = Decimal('10')
_FALLBACK_GRAMS = Decimal('30')


def default_grams_for(ingredient):
    """Placeholder weights for catalog rows. Week-plan portions ignore these."""
    name = ingredient.name.lower()
    if 'olio' in name:
        return _OIL_GRAMS
    if name in _DEFAULT_GRAMS_BY_NAME:
        return _DEFAULT_GRAMS_BY_NAME[name]
    return _DEFAULT_GRAMS_BY_CATEGORY.get(ingredient.category, _FALLBACK_GRAMS)


def resolve_recipe_line(spec, ingredients_by_name):
    resolved = []
    seen = set()
    for key, grams in parse_recipe_items(spec):
        catalog_name = INGREDIENT_ALIASES.get(key)
        if catalog_name is None:
            raise ValueError(f'Unknown ingredient shorthand: {key!r}')
        ingredient = ingredients_by_name.get(catalog_name)
        if ingredient is None:
            raise ValueError(f'Ingredient not in catalog: {catalog_name}')
        if ingredient.id in seen:
            continue
        seen.add(ingredient.id)
        resolved.append((ingredient, grams if grams is not None else default_grams_for(ingredient)))
    return resolved


_COATING_CARB_NAMES = frozenset({'Pangrattato', 'Farina'})
_BREAD_DISH_TOKENS = ('panino', 'sandwich', 'hamburger', 'hummus', 'toast')
_DEFAULT_STAPLE_CARB_BY_GENRE = {
    'pasta_cereali': 'Pasta di semola',
    'pollo_tacchino': 'Riso basmati',
    'pesce': 'Riso basmati',
    'carni_rosse': 'Patata',
    'insaccati': 'Pane integrale',
    'uova': 'Pane integrale',
    'legumi': 'Pane integrale',
    'verdura': 'Patata',
    'formaggio': 'Pane integrale',
    'zuppe': 'Pane integrale',
    'insalate': 'Pane integrale',
    'piadine': 'Piadina',
}


def _has_staple_carb(items):
    return any(
        ingredient.category == IngredientCategory.CARB
        and ingredient.name not in _COATING_CARB_NAMES
        for ingredient, _grams in items
    )


def _default_carb_name(genre, recipe_name):
    lowered = recipe_name.lower()
    if any(token in lowered for token in _BREAD_DISH_TOKENS):
        return 'Pane integrale'
    return _DEFAULT_STAPLE_CARB_BY_GENRE.get(genre, 'Riso basmati')


def ensure_staple_carb(genre, recipe_name, items, ingredients_by_name):
    """Append a side carb when the dish has none (coatings like breadcrumbs do not count)."""
    if _has_staple_carb(items):
        return items
    carb_name = _default_carb_name(genre, recipe_name)
    carb = ingredients_by_name.get(carb_name)
    if carb is None:
        raise ValueError(f'Default carb not in catalog: {carb_name}')
    if any(ingredient.id == carb.id for ingredient, _grams in items):
        return items
    return [*items, (carb, default_grams_for(carb))]


def _rename_ingredients():
    for old, new in INGREDIENT_RENAMES.items():
        if old == new:
            continue
        old_obj = Ingredient.objects.filter(name=old).first()
        if old_obj is None:
            continue
        new_obj = Ingredient.objects.filter(name=new).first()
        if new_obj is None:
            old_obj.name = new
            old_obj.save(update_fields=['name'])
            continue
        for mi in list(old_obj.meal_ingredients.all()):
            exists = MealIngredient.objects.filter(meal=mi.meal, ingredient=new_obj).exists()
            if exists:
                mi.delete()
            else:
                mi.ingredient = new_obj
                mi.save(update_fields=['ingredient'])
        old_obj.delete()


def _rename_system_meals():
    for old, new in SYSTEM_MEAL_RENAMES.items():
        old_meals = list(Meal.objects.filter(is_system=True, name=old))
        if not old_meals:
            continue
        new_meal = Meal.objects.filter(is_system=True, name=new).first()
        if new_meal:
            for old_meal in old_meals:
                WeekPlanSlot.objects.filter(meal=old_meal).update(meal=new_meal)
                old_meal.delete()
            continue
        first, *rest = old_meals
        first.name = new
        first.owner = None
        first.save(update_fields=['name', 'owner'])
        for extra in rest:
            WeekPlanSlot.objects.filter(meal=extra).update(meal=first)
            extra.delete()


def _ensure_tags_and_seasons():
    for name in ALL_YEAR:
        SeasonEntry.objects.get_or_create(name=name)
    for name, tag_type in TAGS:
        Tag.objects.get_or_create(name=name, defaults={'tag_type': tag_type})


def _upsert_ingredient(spec):
    tags = spec['tags']
    seasons = spec['seasons']
    defaults = {
        'category': spec['category'],
        'vegetable_subcategory': spec.get('vegetable_subcategory', ''),
        'kcal': spec['kcal'],
        'protein': spec['protein'],
        'carbs': spec['carbs'],
        'fat': spec['fat'],
        'fiber': spec.get('fiber', '0.00'),
        'sugars': spec.get('sugars', '0.00'),
        'saturated_fat': spec.get('saturated_fat', '0.00'),
        'salt': spec.get('salt', '0.00'),
    }
    obj, created = Ingredient.objects.update_or_create(
        name=spec['name'],
        defaults=defaults,
    )
    obj.tags.set(Tag.objects.filter(name__in=tags))
    obj.seasons.set(SeasonEntry.objects.filter(name__in=seasons))
    return created


def _upsert_system_meal(name, genre, items):
    meal, created = _canonical_system_meal(name, genre)
    meal.meal_ingredients.all().delete()
    MealIngredient.objects.bulk_create(
        [
            MealIngredient(meal=meal, ingredient=ingredient, grams=quantize_grams(grams))
            for ingredient, grams in items
        ]
    )
    return created


def _canonical_system_meal(name, genre):
    meals = list(Meal.objects.filter(is_system=True, name=name).order_by('id'))
    if not meals:
        meal = Meal.objects.create(
            owner=None,
            is_system=True,
            name=name,
            genre=genre,
            description='',
        )
        return meal, True
    meal, extras = meals[0], meals[1:]
    meal.owner = None
    meal.is_system = True
    meal.genre = genre
    meal.description = ''
    meal.save(update_fields=['owner', 'is_system', 'genre', 'description'])
    for extra in extras:
        WeekPlanSlot.objects.filter(meal=extra).update(meal=meal)
        extra.delete()
    return meal, False


def seed_catalog():
    """Idempotent: rename leftovers, upsert ingredients, rebuild system meals."""
    _ensure_tags_and_seasons()
    _rename_ingredients()
    _rename_system_meals()
    created_ingredients = _seed_ingredients()
    created_meals, deleted_meals = _seed_system_meals()
    return {
        'ingredients': Ingredient.objects.count(),
        'created_ingredients': created_ingredients,
        'system_meals': Meal.objects.filter(is_system=True).count(),
        'created_meals': created_meals,
        'deleted_meals': deleted_meals,
    }


def _seed_ingredients():
    created = 0
    for spec in load_ingredient_specs():
        if _upsert_ingredient(spec):
            created += 1
    return created


def _seed_system_meals():
    ingredients_by_name = {ingredient.name: ingredient for ingredient in Ingredient.objects.all()}
    created_meals = 0
    keep_names = set(RECIPE_NAMES)
    for genre, name, spec in RECIPES:
        items = resolve_recipe_line(spec, ingredients_by_name)
        items = ensure_staple_carb(genre, name, items, ingredients_by_name)
        if _upsert_system_meal(name, genre, items):
            created_meals += 1
    deleted_meals = 0
    stale = Meal.objects.filter(is_system=True).exclude(name__in=keep_names)
    for meal in stale:
        if meal.slots.exists():
            continue
        meal.delete()
        deleted_meals += 1
    return created_meals, deleted_meals

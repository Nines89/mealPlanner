from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Ingredient, IngredientCategory, Meal
from .notion_sync import apply_plan, build_plan, prepare_payload


def _recipe(**overrides):
    data = {
        'external_id': 'abc',
        'name': 'Pasta e Zucchina',
        'genre': 'Pasta / Cereali',
        'ingredients': [
            {'name': 'pasta', 'grams': None},
            {'name': 'Zucchine', 'grams': 200},
            {'name': 'ricotta', 'grams': None},
        ],
    }
    data.update(overrides)
    return data


class NotionSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='mario', password='x')
        Ingredient.objects.create(
            name='Pasta di semola', category=IngredientCategory.CARB,
            kcal=353, protein=11, carbs=72, fat=1.8,
        )
        Ingredient.objects.create(
            name='Zucchine', category=IngredientCategory.VEGETABLE,
            vegetable_subcategory='fruit_veg', kcal=17, protein=1.2, carbs=3, fat=0.3,
        )
        Ingredient.objects.create(
            name='Ricotta', category=IngredientCategory.DAIRY,
            kcal=146, protein=8, carbs=3.5, fat=11,
        )

    def _plan(self, *recipes):
        return build_plan(self.user, prepare_payload(list(recipes)))

    def test_preview_does_not_write(self):
        plan = self._plan(_recipe())
        self.assertEqual(len(plan.new), 1)
        self.assertFalse(Meal.objects.filter(external_id='abc').exists())

    def test_apply_creates_then_second_run_is_unchanged(self):
        apply_plan(self._plan(_recipe()), self.user)
        meal = Meal.objects.get(external_id='abc')
        self.assertEqual(meal.owner, self.user)
        self.assertFalse(meal.is_system)
        self.assertEqual(meal.source, 'notion')
        self.assertEqual(meal.genre, 'pasta_cereali')
        plan = self._plan(_recipe())
        self.assertEqual(len(plan.unchanged), 1)
        self.assertFalse(plan.has_changes)

    def test_changed_grams_are_reported_and_applied(self):
        apply_plan(self._plan(_recipe()), self.user)
        changed = _recipe(ingredients=[
            {'name': 'pasta', 'grams': None},
            {'name': 'Zucchine', 'grams': 150},
            {'name': 'ricotta', 'grams': None},
        ])
        plan = self._plan(changed)
        self.assertEqual(len(plan.updates), 1)
        self.assertTrue(any('Zucchine' in c for c in plan.updates[0].changes))
        apply_plan(plan, self.user)
        row = Meal.objects.get(external_id='abc').meal_ingredients.get(ingredient__name='Zucchine')
        self.assertEqual(row.grams, 150)

    def test_rename_keeps_same_meal(self):
        apply_plan(self._plan(_recipe()), self.user)
        meal_id = Meal.objects.get(external_id='abc').id
        apply_plan(self._plan(_recipe(name='Pasta con Zucchine')), self.user)
        self.assertEqual(Meal.objects.get(external_id='abc').id, meal_id)
        self.assertEqual(Meal.objects.filter(source='notion').count(), 1)

    def test_unknown_ingredient_is_an_error_and_not_written(self):
        bad = _recipe(ingredients=[{'name': 'unobtainium', 'grams': 10}])
        plan = self._plan(bad)
        self.assertEqual(len(plan.errors), 1)
        apply_plan(plan, self.user)
        self.assertFalse(Meal.objects.filter(external_id='abc').exists())

    def test_invalid_genre_is_rejected(self):
        plan = self._plan(_recipe(genre='boh'))
        self.assertEqual(len(plan.errors), 1)

    def test_orphans_are_reported_and_prune_guards_empty_input(self):
        apply_plan(self._plan(_recipe()), self.user)
        empty_plan = build_plan(self.user, prepare_payload([]))
        self.assertEqual(len(empty_plan.orphans), 1)
        apply_plan(empty_plan, self.user, prune=True)
        self.assertTrue(Meal.objects.filter(external_id='abc').exists())
        other = _recipe(external_id='xyz', name='Altra pasta')
        apply_plan(self._plan(other), self.user, prune=True)
        self.assertFalse(Meal.objects.filter(external_id='abc').exists())

    def test_local_edit_survives_when_notion_is_unchanged(self):
        apply_plan(self._plan(_recipe()), self.user)
        meal = Meal.objects.get(external_id='abc')
        meal.meal_ingredients.filter(ingredient__name='Zucchine').update(grams=Decimal('300'))
        plan = self._plan(_recipe())
        self.assertEqual(len(plan.unchanged), 1)
        apply_plan(plan, self.user)
        row = meal.meal_ingredients.get(ingredient__name='Zucchine')
        self.assertEqual(row.grams, Decimal('300'))

    def test_notion_change_overrides_local_edit_with_warning(self):
        apply_plan(self._plan(_recipe()), self.user)
        meal = Meal.objects.get(external_id='abc')
        meal.meal_ingredients.filter(ingredient__name='Zucchine').update(grams=Decimal('300'))
        changed = _recipe(ingredients=[
            {'name': 'pasta', 'grams': None},
            {'name': 'Zucchine', 'grams': 150},
            {'name': 'ricotta', 'grams': None},
        ])
        plan = self._plan(changed)
        self.assertEqual(len(plan.updates), 1)
        self.assertTrue(plan.updates[0].warnings)
        apply_plan(plan, self.user)
        row = meal.meal_ingredients.get(ingredient__name='Zucchine')
        self.assertEqual(row.grams, Decimal('150'))

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .catalog import seed_catalog
from .models import Ingredient, IngredientCategory, Meal, MealIngredient


class RecipeViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='mario', password='x')
        cls.other = User.objects.create_user(username='luigi', password='x')
        cls.pasta = Ingredient.objects.create(
            name='Pasta di semola', category=IngredientCategory.CARB,
            kcal=353, protein=11, carbs=72, fat=1.8,
        )
        cls.zucchine = Ingredient.objects.create(
            name='Zucchine', category=IngredientCategory.VEGETABLE,
            vegetable_subcategory='fruit_veg', kcal=17, protein=1.2, carbs=3, fat=0.3,
        )
        cls.meal = Meal.objects.create(owner=cls.user, name='Pasta X', genre='pasta_cereali')
        MealIngredient.objects.create(meal=cls.meal, ingredient=cls.pasta, grams=Decimal('80'))
        MealIngredient.objects.create(meal=cls.meal, ingredient=cls.zucchine, grams=Decimal('200'))

    def setUp(self):
        self.client.force_login(self.user)

    def _post_data(self, **overrides):
        rows = list(self.meal.meal_ingredients.order_by('id'))
        prefix = 'meal_ingredients'
        data = {
            'name': 'Pasta Y',
            'genre': 'pesce',
            f'{prefix}-TOTAL_FORMS': str(len(rows) + 1),
            f'{prefix}-INITIAL_FORMS': str(len(rows)),
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
            f'{prefix}-{len(rows)}-ingredient': '',
            f'{prefix}-{len(rows)}-grams': '',
        }
        for i, row in enumerate(rows):
            data[f'{prefix}-{i}-id'] = str(row.id)
            data[f'{prefix}-{i}-meal'] = str(self.meal.id)
            data[f'{prefix}-{i}-ingredient'] = str(row.ingredient_id)
            data[f'{prefix}-{i}-grams'] = str(row.grams)
        data.update(overrides)
        return data

    def test_list_groups_recipes_by_category(self):
        response = self.client.get(reverse('core:recipes'))
        self.assertContains(response, 'Pasta X')
        self.assertContains(response, 'Pasta / Cereali')

    def test_list_search_filters_by_name(self):
        response = self.client.get(reverse('core:recipes'), {'q': 'zzz'})
        self.assertNotContains(response, 'Pasta X')

    def test_edit_saves_and_quantizes_grams(self):
        data = self._post_data(**{'meal_ingredients-0-grams': '85'})
        response = self.client.post(reverse('core:recipe_edit', args=[self.meal.id]), data)
        self.assertEqual(response.status_code, 302)
        self.meal.refresh_from_db()
        self.assertEqual(self.meal.name, 'Pasta Y')
        self.assertEqual(self.meal.genre, 'pesce')
        row = self.meal.meal_ingredients.get(ingredient=self.pasta)
        self.assertEqual(row.grams, Decimal('90'))

    def test_edit_without_ingredients_is_rejected(self):
        data = self._post_data(**{
            'meal_ingredients-0-DELETE': 'on',
            'meal_ingredients-1-DELETE': 'on',
        })
        response = self.client.post(reverse('core:recipe_edit', args=[self.meal.id]), data)
        self.assertEqual(response.status_code, 200)
        self.meal.refresh_from_db()
        self.assertEqual(self.meal.name, 'Pasta X')
        self.assertEqual(self.meal.meal_ingredients.count(), 2)

    def test_cannot_edit_another_users_recipe(self):
        foreign = Meal.objects.create(owner=self.other, name='Privata', genre='pesce')
        response = self.client.get(reverse('core:recipe_edit', args=[foreign.id]))
        self.assertEqual(response.status_code, 404)

    def test_seed_catalog_keeps_customized_system_meals(self):
        seed_catalog()
        meal = Meal.objects.get(is_system=True, name='Pasta e Zucchina')
        meal.meal_ingredients.filter(ingredient__name='Ricotta').delete()
        Meal.objects.filter(pk=meal.pk).update(customized=True, seed_key='Pasta e Zucchina')
        before = meal.meal_ingredients.count()
        seed_catalog()
        self.assertEqual(meal.meal_ingredients.count(), before)

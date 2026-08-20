from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .macros import empty_macros, macros_for_grams, sum_macros
from .models import (
    DayKind,
    Household,
    HouseholdMember,
    Ingredient,
    IngredientCategory,
    Meal,
    MealGenre,
    MealIngredient,
    MealSlot,
    NutritionTarget,
    WeekPlan,
    WeekPlanDayKind,
    WeekPlanSlot,
)
from .catalog import SYSTEM_MEALS, load_ingredient_specs, seed_catalog
from .nutrition import compute_week_totals, plate_macros_for_meal
from .planning import (
    GENERATED_MEAL_MARKER,
    MIN_DAY_COVERAGE,
    MAX_DAY_COVERAGE,
    VEG_MIN_GRAMS,
    PlateSelection,
    daily_macros,
    fit_day_coverage,
    scale_plate,
    shopping_list_for_plan,
)
from .targets import ensure_on_off_targets, get_target_by_kind
from .week import monday_of_week


def _ing(**kwargs):
    data = {
        'name': 'x',
        'kcal': Decimal('0'),
        'protein': Decimal('0'),
        'carbs': Decimal('0'),
        'fat': Decimal('0'),
    }
    data.update(kwargs)
    for key in ('kcal', 'protein', 'carbs', 'fat'):
        data[key] = Decimal(str(data[key]))
    return SimpleNamespace(**data)


def _attach_template_plate(meal, protein, carb, vegetable, fat):
    MealIngredient.objects.create(meal=meal, ingredient=protein, grams=Decimal('10.0'))
    MealIngredient.objects.create(meal=meal, ingredient=carb, grams=Decimal('80.0'))
    MealIngredient.objects.create(meal=meal, ingredient=vegetable, grams=Decimal('200.0'))
    MealIngredient.objects.create(meal=meal, ingredient=fat, grams=Decimal('15.0'))


def _day_coverage_ratios(lunch, dinner, target):
    combined = sum_macros(plate_macros_for_meal(lunch), plate_macros_for_meal(dinner))
    daily = daily_macros(target)
    return {
        name: combined[name] / daily[name]
        for name in daily
        if daily[name] > 0 and combined[name] > 0
    }


class WeekPlanMealGridTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='mario', password='secret')
        cls.lunch_slot = MealSlot.objects.get(user=cls.user, name='Lunch')
        cls.dinner_slot = MealSlot.objects.get(user=cls.user, name='Dinner')
        cls.soup = Meal.objects.create(
            name='Zuppa di Carote',
            is_system=True,
            genre=MealGenre.ZUPPE,
        )
        cls.fish = Meal.objects.create(
            name='Orata al forno',
            is_system=True,
            genre=MealGenre.PESCE,
        )
        cls.chicken = Ingredient.objects.create(
            name='Chicken',
            category=IngredientCategory.PROTEIN,
            kcal=110,
            protein=23,
            carbs=0,
            fat=2,
        )
        cls.rice = Ingredient.objects.create(
            name='Rice',
            category=IngredientCategory.CARB,
            kcal=130,
            protein=2.7,
            carbs=28,
            fat=0.3,
        )
        cls.broccoli = Ingredient.objects.create(
            name='Broccoli',
            category=IngredientCategory.VEGETABLE,
            vegetable_subcategory='flower',
            kcal=34,
            protein=2.8,
            carbs=7,
            fat=0.4,
        )
        cls.oil = Ingredient.objects.create(
            name='Oil',
            category=IngredientCategory.FAT,
            kcal=884,
            protein=0,
            carbs=0,
            fat=100,
        )
        _attach_template_plate(cls.soup, cls.chicken, cls.rice, cls.broccoli, cls.oil)
        _attach_template_plate(cls.fish, cls.chicken, cls.rice, cls.broccoli, cls.oil)
        ensure_on_off_targets()

    def setUp(self):
        self.client.force_login(self.user)

    def _post_grid(self, assignments, form_id='meal_grid'):
        data = {'form_id': form_id}
        for meal_slot in (self.lunch_slot, self.dinner_slot):
            for day in range(7):
                data[f'genre_{day}_{meal_slot.id}'] = assignments.get((day, meal_slot.id), '')
        return self.client.post(reverse('core:week_plan'), data)

    def test_user_can_assign_categories_to_week_grid(self):
        response = self._post_grid(
            {
                (0, self.lunch_slot.id): MealGenre.ZUPPE,
                (0, self.dinner_slot.id): MealGenre.PESCE,
            }
        )

        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        lunch = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.lunch_slot
        )
        dinner = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.dinner_slot
        )
        self.assertEqual(lunch.genre, MealGenre.ZUPPE)
        self.assertIsNone(lunch.meal)
        self.assertEqual(dinner.genre, MealGenre.PESCE)
        self.assertIsNone(dinner.meal)

    def test_user_can_update_and_clear_categories(self):
        week_plan = WeekPlan.objects.create(owner=self.user, week_start=monday_of_week())
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=0,
            meal_slot=self.lunch_slot,
            genre=MealGenre.ZUPPE,
            meal=self.soup,
        )
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=0,
            meal_slot=self.dinner_slot,
            genre=MealGenre.PESCE,
            meal=self.fish,
        )

        response = self._post_grid(
            {
                (0, self.lunch_slot.id): MealGenre.PESCE,
                (0, self.dinner_slot.id): '',
            }
        )

        self.assertRedirects(response, reverse('core:week_plan'))
        lunch = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.lunch_slot
        )
        self.assertEqual(lunch.genre, MealGenre.PESCE)
        self.assertIsNone(lunch.meal)
        self.assertFalse(
            WeekPlanSlot.objects.filter(
                week_plan=week_plan,
                day=0,
                meal_slot=self.dinner_slot,
            ).exists()
        )

    def test_invalid_category_is_ignored(self):
        response = self._post_grid({(0, self.lunch_slot.id): 'not-a-genre'})
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        self.assertFalse(
            WeekPlanSlot.objects.filter(
                week_plan=week_plan,
                day=0,
                meal_slot=self.lunch_slot,
            ).exists()
        )

    def test_build_assigns_a_dish_from_each_category(self):
        response = self._post_grid(
            {
                (0, self.lunch_slot.id): MealGenre.ZUPPE,
                (0, self.dinner_slot.id): MealGenre.PESCE,
            },
            form_id='build',
        )
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        lunch = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.lunch_slot
        )
        dinner = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.dinner_slot
        )
        self.assertEqual(lunch.genre, MealGenre.ZUPPE)
        self.assertEqual(lunch.meal.name, 'Zuppa di Carote')
        self.assertNotEqual(lunch.meal.id, self.soup.id)
        self.assertEqual(lunch.meal.description, GENERATED_MEAL_MARKER)
        self.assertEqual(dinner.genre, MealGenre.PESCE)
        self.assertEqual(dinner.meal.name, 'Orata al forno')
        self.assertNotEqual(
            lunch.meal.meal_ingredients.get(ingredient=self.chicken).grams,
            Decimal('10.0'),
        )
        off = get_target_by_kind(DayKind.OFF)
        slack = Decimal('0.01')
        for ratio in _day_coverage_ratios(lunch.meal, dinner.meal, off).values():
            self.assertGreaterEqual(ratio, MIN_DAY_COVERAGE - slack)
            self.assertLessEqual(ratio, MAX_DAY_COVERAGE + slack)

    def test_build_leaves_category_when_catalog_is_empty(self):
        response = self._post_grid(
            {(0, self.lunch_slot.id): MealGenre.UOVA},
            form_id='build',
        )
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        lunch = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.lunch_slot
        )
        self.assertEqual(lunch.genre, MealGenre.UOVA)
        self.assertIsNone(lunch.meal)

    def test_week_plan_has_build_and_no_fill_links(self):
        response = self.client.get(reverse('core:week_plan'))
        self.assertContains(response, 'Build')
        self.assertNotContains(response, '/fill/')

    def test_user_can_save_on_off_days(self):
        data = {'form_id': 'day_kinds'}
        for day in range(7):
            data[f'day_kind_{day}'] = 'on' if day < 5 else 'off'
        response = self.client.post(reverse('core:week_plan'), data)
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        kinds = dict(
            WeekPlanDayKind.objects.filter(week_plan=week_plan).values_list('day', 'kind')
        )
        self.assertEqual(kinds[0], DayKind.ON)
        self.assertEqual(kinds[5], DayKind.OFF)


class ScalePlateTests(TestCase):
    def test_protein_grams_hit_slot_protein(self):
        protein = _ing(name='chicken', kcal=110, protein=23, carbs=0, fat=2)
        vegetable = _ing(name='broccoli', kcal=34, protein=2.8, carbs=7, fat=0.4)
        budget = {
            'kcal': Decimal('800'),
            'protein': Decimal('46'),
            'carbs': Decimal('80'),
            'fat': Decimal('28'),
        }
        items = scale_plate(budget, PlateSelection(protein, vegetable))
        by_name = {ing.name: grams for ing, grams in items}
        self.assertEqual(by_name['chicken'], Decimal('200.0'))
        self.assertEqual(by_name['broccoli'], Decimal('1706'))
        for grams in by_name.values():
            self.assertEqual(grams, grams.to_integral_value())

    def test_optional_carb_and_fat_fill_remainders(self):
        protein = _ing(name='chicken', kcal=110, protein=23, carbs=0, fat=2)
        vegetable = _ing(name='broccoli', kcal=34, protein=2.8, carbs=7, fat=0.4)
        carb = _ing(name='rice', kcal=130, protein=2.7, carbs=28, fat=0.3)
        fat = _ing(name='oil', kcal=884, protein=0, carbs=0, fat=100)
        budget = {
            'kcal': Decimal('800'),
            'protein': Decimal('46'),
            'carbs': Decimal('80'),
            'fat': Decimal('28'),
        }
        items = scale_plate(budget, PlateSelection(protein, vegetable, carb=carb, fat=fat))
        by_name = {ing.name: grams for ing, grams in items}
        self.assertEqual(by_name['chicken'], Decimal('200.0'))
        self.assertEqual(by_name['rice'], Decimal('286'))
        self.assertEqual(by_name['oil'], Decimal('23'))
        self.assertEqual(by_name['broccoli'], Decimal('150'))
        for grams in by_name.values():
            self.assertEqual(grams, grams.to_integral_value())

    def test_two_plates_fit_day_coverage_band(self):
        chicken = _ing(
            name='chicken',
            kcal=110,
            protein=23,
            carbs=0,
            fat=2,
            category=IngredientCategory.PROTEIN,
        )
        oversized = [(chicken, Decimal('1000.0'))]
        daily = {
            'kcal': Decimal('1500'),
            'protein': Decimal('75'),
            'carbs': Decimal('178'),
            'fat': Decimal('38'),
        }
        fitted = fit_day_coverage(daily, [oversized, oversized])
        combined = empty_macros()
        for plate in fitted:
            for ingredient, grams in plate:
                combined = sum_macros(combined, macros_for_grams(ingredient, grams))
        protein_ratio = combined['protein'] / daily['protein']
        self.assertLessEqual(protein_ratio, MAX_DAY_COVERAGE)
        self.assertGreaterEqual(protein_ratio, MIN_DAY_COVERAGE)


class FillSlotViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='mario', password='secret')
        cls.lunch_slot = MealSlot.objects.get(user=cls.user, name='Lunch')
        cls.chicken = Ingredient.objects.create(
            name='Chicken breast',
            category=IngredientCategory.PROTEIN,
            kcal=110,
            protein=23,
            carbs=0,
            fat=2,
        )
        cls.broccoli = Ingredient.objects.create(
            name='Broccoli',
            category=IngredientCategory.VEGETABLE,
            vegetable_subcategory='flower',
            kcal=34,
            protein=2.8,
            carbs=7,
            fat=0.4,
        )
        ensure_on_off_targets()

    def setUp(self):
        self.client.force_login(self.user)

    def test_fill_page_renders(self):
        url = reverse('core:week_plan_fill', args=[0, self.lunch_slot.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Semi-manual')

    def test_semi_manual_fill_creates_scaled_meal(self):
        url = reverse('core:week_plan_fill', args=[0, self.lunch_slot.id])
        response = self.client.post(
            url,
            {
                'mode': 'semi_manual',
                'protein': str(self.chicken.id),
                'vegetable': str(self.broccoli.id),
            },
        )
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        slot = WeekPlanSlot.objects.get(week_plan=week_plan, day=0, meal_slot=self.lunch_slot)
        self.assertEqual(slot.meal.owner, self.user)
        names = set(slot.meal.meal_ingredients.values_list('ingredient__name', flat=True))
        self.assertEqual(names, {'Chicken breast', 'Broccoli'})
        chicken_row = slot.meal.meal_ingredients.get(ingredient=self.chicken)
        self.assertGreater(chicken_row.grams, 0)

    def test_fill_keeps_selected_category(self):
        week_plan = WeekPlan.objects.create(owner=self.user, week_start=monday_of_week())
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=0,
            meal_slot=self.lunch_slot,
            genre=MealGenre.ZUPPE,
            meal=None,
        )
        url = reverse('core:week_plan_fill', args=[0, self.lunch_slot.id])
        response = self.client.post(
            url,
            {
                'mode': 'semi_manual',
                'protein': str(self.chicken.id),
                'vegetable': str(self.broccoli.id),
            },
        )
        self.assertRedirects(response, reverse('core:week_plan'))
        slot = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=0, meal_slot=self.lunch_slot
        )
        self.assertEqual(slot.genre, MealGenre.ZUPPE)
        self.assertEqual(slot.meal.genre, MealGenre.ZUPPE)

    def test_semi_auto_fill_picks_a_vegetable(self):
        url = reverse('core:week_plan_fill', args=[1, self.lunch_slot.id])
        response = self.client.post(
            url,
            {
                'mode': 'semi_auto',
                'protein': str(self.chicken.id),
            },
        )
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        slot = WeekPlanSlot.objects.get(week_plan=week_plan, day=1, meal_slot=self.lunch_slot)
        names = set(slot.meal.meal_ingredients.values_list('ingredient__name', flat=True))
        self.assertIn('Chicken breast', names)
        self.assertIn('Broccoli', names)

    def test_automatic_fill_picks_protein_and_vegetable(self):
        url = reverse('core:week_plan_fill', args=[2, self.lunch_slot.id])
        response = self.client.post(url, {'mode': 'automatic'})
        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        slot = WeekPlanSlot.objects.get(week_plan=week_plan, day=2, meal_slot=self.lunch_slot)
        self.assertEqual(slot.meal.meal_ingredients.count(), 2)

    def test_fill_uses_off_budget_by_default(self):
        url = reverse('core:week_plan_fill', args=[0, self.lunch_slot.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OFF')
        self.assertContains(response, '1500 kcal')
        # Lunch is half of the OFF day (1500 → 750).
        self.assertEqual(response.context['budget']['kcal'], Decimal('750'))

    def test_fill_uses_on_budget_when_day_is_on(self):
        week_plan = WeekPlan.objects.create(owner=self.user, week_start=monday_of_week())
        WeekPlanDayKind.objects.create(week_plan=week_plan, day=0, kind=DayKind.ON)
        url = reverse('core:week_plan_fill', args=[0, self.lunch_slot.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ON')
        self.assertContains(response, '1700 kcal')
        self.assertEqual(response.context['budget']['kcal'], Decimal('850'))


class NutritionAndShoppingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='mario', password='secret')
        cls.lunch_slot = MealSlot.objects.get(user=cls.user, name='Lunch')
        cls.chicken = Ingredient.objects.create(
            name='Chicken',
            category=IngredientCategory.PROTEIN,
            kcal=100,
            protein=20,
            carbs=0,
            fat=2,
        )
        meal = Meal.objects.create(name='Plate', owner=cls.user)
        MealIngredient.objects.create(meal=meal, ingredient=cls.chicken, grams=Decimal('100.0'))
        cls.meal = meal
        ensure_on_off_targets()
        household = Household.ensure_for_user(cls.user)
        HouseholdMember.objects.create(household=household, display_name='Partner', sort_order=1)
        cls.week_plan = WeekPlan.objects.create(
            owner=cls.user,
            week_start=monday_of_week(),
        )
        cls.slot = WeekPlanSlot.objects.create(
            week_plan=cls.week_plan,
            day=0,
            meal_slot=cls.lunch_slot,
            meal=meal,
        )

    def test_household_totals_multiply_by_member_count(self):
        household = Household.objects.get(owner=self.user)
        n = household.member_count()
        self.assertEqual(n, 2)
        off = get_target_by_kind(DayKind.OFF)
        totals = compute_week_totals({d: off for d in range(7)}, [self.slot], n)
        self.assertEqual(totals['by_week']['expected']['kcal'], Decimal('1500') * n * 7)
        # 100 g chicken at 100 kcal / 100 g → 100 kcal per plate × 2 people
        self.assertEqual(totals['by_day'][0]['effective']['kcal'], Decimal('200'))
        self.assertEqual(totals['by_week']['effective']['kcal'], Decimal('200'))

    def test_on_day_raises_expected_kcal(self):
        household = Household.objects.get(owner=self.user)
        n = household.member_count()
        on = get_target_by_kind(DayKind.ON)
        off = get_target_by_kind(DayKind.OFF)
        day_targets = {d: off for d in range(7)}
        day_targets[0] = on
        totals = compute_week_totals(day_targets, [self.slot], n)
        self.assertEqual(
            totals['by_week']['expected']['kcal'],
            Decimal('1700') * n + Decimal('1500') * n * 6,
        )

    def test_shopping_list_multiplies_grams(self):
        rows = shopping_list_for_plan(self.week_plan, member_count=2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Chicken')
        self.assertEqual(rows[0]['grams'], Decimal('200.0'))

    def test_shopping_list_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('core:shopping_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chicken')
        self.assertContains(response, '200 g')


class NoLoginRequiredTests(TestCase):
    def test_dashboard_opens_without_login(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Log in')
        self.assertNotContains(response, 'Register')
        self.assertContains(response, 'Week plan')

    def test_week_plan_has_no_breakfast_row(self):
        response = self.client.get(reverse('core:week_plan'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Breakfast')
        self.assertNotContains(response, 'Colazione')
        self.assertContains(response, 'Lunch')
        self.assertContains(response, 'Dinner')


class OnOffTargetTests(TestCase):
    def test_ensure_replaces_other_targets(self):
        NutritionTarget.objects.create(name='Old cut', target_kcal=2200)
        NutritionTarget.objects.create(name='Old bulk', target_kcal=2800)
        ensure_on_off_targets()
        remaining = list(NutritionTarget.objects.order_by('kind'))
        self.assertEqual(len(remaining), 2)
        by_kind = {row.kind: row for row in remaining}
        self.assertEqual(by_kind[DayKind.ON].target_kcal, 1700)
        self.assertEqual(by_kind[DayKind.OFF].target_kcal, 1500)
        self.assertEqual(by_kind[DayKind.ON].protein_pct_min, 15)
        self.assertEqual(by_kind[DayKind.ON].protein_pct_max, 25)
        self.assertEqual(by_kind[DayKind.ON].fat_pct_min, 20)
        self.assertEqual(by_kind[DayKind.ON].fat_pct_max, 25)
        self.assertEqual(by_kind[DayKind.ON].carbs_pct_min, 45)
        self.assertEqual(by_kind[DayKind.ON].carbs_pct_max, 50)
        self.assertEqual(by_kind[DayKind.ON].target_protein, 85)
        self.assertEqual(by_kind[DayKind.OFF].target_protein, 75)

    def test_ensure_does_not_overwrite_admin_edits(self):
        ensure_on_off_targets()
        on = NutritionTarget.objects.get(kind=DayKind.ON)
        on.target_kcal = 1800
        on.protein_pct_min = 20
        on.protein_pct_max = 30
        on.save()
        on.refresh_from_db()
        self.assertEqual(on.target_kcal, 1800)
        self.assertEqual(on.target_protein, 113)
        ensure_on_off_targets()
        on.refresh_from_db()
        self.assertEqual(on.target_kcal, 1800)
        self.assertEqual(on.protein_pct_min, 20)
        self.assertEqual(on.protein_pct_max, 30)
        self.assertEqual(on.target_protein, 113)

    def test_dashboard_shows_on_and_off(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1700')
        self.assertContains(response, '1500')
        self.assertEqual(NutritionTarget.objects.count(), 2)


class CatalogSeedTests(TestCase):
    def test_seed_creates_complete_system_meals(self):
        seed_catalog()
        meals = Meal.objects.filter(is_system=True)
        self.assertEqual(meals.count(), len(set(SYSTEM_MEALS)))
        chicken = meals.get(name='Pasta e Zucchina')
        names = set(
            chicken.meal_ingredients.values_list('ingredient__name', flat=True)
        )
        self.assertEqual(names, {'Pasta di semola', 'Zucchine', 'Ricotta'})
        self.assertEqual(chicken.genre, 'pasta_cereali')
        self.assertEqual(
            chicken.meal_ingredients.get(ingredient__name='Zucchine').grams,
            Decimal('200.0'),
        )

    def test_seed_adds_a_staple_carb_when_missing(self):
        seed_catalog()
        chicken = Meal.objects.get(is_system=True, name='Pollo e zucchine')
        names = set(chicken.meal_ingredients.values_list('ingredient__name', flat=True))
        self.assertIn('Riso basmati', names)
        meatballs = Meal.objects.get(is_system=True, name='Polpette di macinato')
        meatball_names = set(
            meatballs.meal_ingredients.values_list('ingredient__name', flat=True)
        )
        self.assertIn('Patata', meatball_names)
        hummus = Meal.objects.get(is_system=True, name='Hummus e pane Arabo')
        hummus_names = set(hummus.meal_ingredients.values_list('ingredient__name', flat=True))
        self.assertIn('Pane integrale', hummus_names)

    def test_seed_system_meals_all_have_a_staple_carb(self):
        seed_catalog()
        coating = {'Pangrattato', 'Farina'}
        for meal in Meal.objects.filter(is_system=True).prefetch_related(
            'meal_ingredients__ingredient'
        ):
            staples = [
                row.ingredient.name
                for row in meal.meal_ingredients.all()
                if row.ingredient.category == IngredientCategory.CARB
                and row.ingredient.name not in coating
            ]
            self.assertTrue(staples, msg=f'{meal.name} has no staple carb')

    def test_seed_is_idempotent_and_renames_italian_leftovers(self):
        user = User.objects.create_user(username='planner', password='secret')
        Ingredient.objects.create(
            name='Chicken breast',
            category=IngredientCategory.PROTEIN,
            kcal=110,
            protein=23,
            carbs=0,
            fat=1.5,
        )
        Meal.objects.create(name='Pasta e Zucchina', is_system=True, owner=user)
        seed_catalog()
        seed_catalog()
        self.assertFalse(Ingredient.objects.filter(name='Chicken breast').exists())
        self.assertTrue(Ingredient.objects.filter(name='Petto di pollo').exists())
        pasta_meals = Meal.objects.filter(is_system=True, name='Pasta e Zucchina')
        self.assertEqual(pasta_meals.count(), 1)
        self.assertIsNone(pasta_meals.get().owner_id)
        self.assertEqual(
            Meal.objects.filter(is_system=True).count(),
            len(set(SYSTEM_MEALS)),
        )

    def test_ingredients_csv_is_valid_and_unique(self):
        specs = load_ingredient_specs()
        names = [row['name'] for row in specs]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(specs), 150)
        categories = {row['category'] for row in specs}
        self.assertTrue(
            {'protein', 'vegetable', 'carb', 'fat'}.issubset(categories)
        )
        seed_catalog()
        self.assertGreaterEqual(Ingredient.objects.count(), 150)
        self.assertTrue(Ingredient.objects.filter(name='Pancetta').exists())
        self.assertTrue(Ingredient.objects.filter(name='Piadina').exists())

    def test_week_plan_lists_recipe_categories(self):
        self.client.force_login(User.objects.create_user(username='nino', password='secret'))
        response = self.client.get(reverse('core:week_plan'))
        self.assertContains(response, 'Pasta / Cereali')
        self.assertContains(response, 'Pollo / Tacchino')
        self.assertContains(response, 'Zuppe')
        self.assertNotContains(response, 'Pasta e Zucchina')


class DashboardTodayTests(TestCase):
    def test_dashboard_lists_todays_assigned_meal(self):
        user = User.objects.create_user(username='gio', password='secret')
        lunch = MealSlot.objects.get(user=user, name='Lunch')
        pasta = Ingredient.objects.create(
            name='Pasta di semola',
            category=IngredientCategory.CARB,
            kcal=353,
            protein=11,
            carbs=72,
            fat=1.8,
        )
        meal = Meal.objects.create(name='Pasta e Zucchina', owner=user)
        MealIngredient.objects.create(meal=meal, ingredient=pasta, grams=Decimal('80.0'))
        week_plan = WeekPlan.objects.create(owner=user, week_start=monday_of_week())
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=date.today().weekday(),
            meal_slot=lunch,
            meal=meal,
        )
        self.client.force_login(user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pasta e Zucchina')
        self.assertContains(response, 'Pasta di semola')
        self.assertContains(response, 'Per plate')
        self.assertContains(response, 'Lunch')

    def test_dashboard_rescales_today_to_the_household_plan(self):
        user = User.objects.create_user(username='casa', password='secret')
        lunch = MealSlot.objects.get(user=user, name='Lunch')
        dinner = MealSlot.objects.get(user=user, name='Dinner')
        chicken = Ingredient.objects.create(
            name='Chicken',
            category=IngredientCategory.PROTEIN,
            kcal=110,
            protein=23,
            carbs=0,
            fat=2,
        )
        rice = Ingredient.objects.create(
            name='Rice',
            category=IngredientCategory.CARB,
            kcal=130,
            protein=2.7,
            carbs=28,
            fat=0.3,
        )
        broccoli = Ingredient.objects.create(
            name='Broccoli',
            category=IngredientCategory.VEGETABLE,
            vegetable_subcategory='flower',
            kcal=34,
            protein=2.8,
            carbs=7,
            fat=0.4,
        )
        oil = Ingredient.objects.create(
            name='Oil',
            category=IngredientCategory.FAT,
            kcal=884,
            protein=0,
            carbs=0,
            fat=100,
        )
        soup = Meal.objects.create(
            name='Zuppa di Carote', is_system=True, genre=MealGenre.ZUPPE
        )
        fish = Meal.objects.create(
            name='Orata al forno', is_system=True, genre=MealGenre.PESCE
        )
        _attach_template_plate(soup, chicken, rice, broccoli, oil)
        _attach_template_plate(fish, chicken, rice, broccoli, oil)
        household = Household.ensure_for_user(user)
        HouseholdMember.objects.create(household=household, display_name='Partner', sort_order=1)
        ensure_on_off_targets()
        week_plan = WeekPlan.objects.create(owner=user, week_start=monday_of_week())
        today = date.today().weekday()
        WeekPlanSlot.objects.create(
            week_plan=week_plan, day=today, meal_slot=lunch, meal=soup, genre=MealGenre.ZUPPE
        )
        WeekPlanSlot.objects.create(
            week_plan=week_plan, day=today, meal_slot=dinner, meal=fish, genre=MealGenre.PESCE
        )
        self.client.force_login(user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        lunch_slot = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=today, meal_slot=lunch
        )
        self.assertFalse(lunch_slot.meal.is_system)
        dinner_slot = WeekPlanSlot.objects.get(
            week_plan=week_plan, day=today, meal_slot=dinner
        )
        for plan_slot in (lunch_slot, dinner_slot):
            veg_rows = [
                row
                for row in plan_slot.meal.meal_ingredients.select_related('ingredient')
                if row.ingredient.category == IngredientCategory.VEGETABLE
            ]
            self.assertTrue(veg_rows)
            for row in veg_rows:
                self.assertGreaterEqual(row.grams, VEG_MIN_GRAMS)
        effective = response.context['day_effective']['kcal']
        expected = response.context['day_expected']['kcal']
        self.assertEqual(expected, Decimal('3000'))
        ratio = effective / expected
        self.assertGreaterEqual(ratio, Decimal('0.848'))
        self.assertLessEqual(ratio, Decimal('1.002'))




from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Meal, MealSlot, MealSlotDefault, WeekPlan, WeekPlanSlot
from .views import monday_of_week


class WeekPlanMealGridTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        MealSlotDefault.objects.create(name='Colazione', order=0)
        MealSlotDefault.objects.create(name='Pranzo', order=1)

        cls.user = User.objects.create_user(username='mario', password='secret')
        cls.other_user = User.objects.create_user(username='luigi', password='secret')
        cls.breakfast_slot = MealSlot.objects.get(user=cls.user, name='Colazione')
        cls.lunch_slot = MealSlot.objects.get(user=cls.user, name='Pranzo')

        cls.system_meal = Meal.objects.create(name='Porridge', is_system=True)
        cls.private_meal = Meal.objects.create(name='Pasta personale', owner=cls.user)
        cls.other_private_meal = Meal.objects.create(name='Pasto privato altrui', owner=cls.other_user)

    def setUp(self):
        self.client.force_login(self.user)

    def _post_grid(self, assignments):
        data = {'form_id': 'meal_grid'}
        for meal_slot in (self.breakfast_slot, self.lunch_slot):
            for day in range(7):
                data[f'meal_{day}_{meal_slot.id}'] = assignments.get((day, meal_slot.id), '')
        return self.client.post(reverse('core:week_plan'), data)

    def test_user_can_assign_meals_to_week_grid(self):
        response = self._post_grid(
            {
                (0, self.breakfast_slot.id): str(self.system_meal.id),
                (0, self.lunch_slot.id): str(self.private_meal.id),
            }
        )

        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        self.assertEqual(
            WeekPlanSlot.objects.get(
                week_plan=week_plan,
                day=0,
                meal_slot=self.breakfast_slot,
            ).meal,
            self.system_meal,
        )
        self.assertEqual(
            WeekPlanSlot.objects.get(
                week_plan=week_plan,
                day=0,
                meal_slot=self.lunch_slot,
            ).meal,
            self.private_meal,
        )

    def test_user_can_update_and_clear_existing_meal_assignments(self):
        week_plan = WeekPlan.objects.create(owner=self.user, week_start=monday_of_week())
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=0,
            meal_slot=self.breakfast_slot,
            meal=self.system_meal,
        )
        WeekPlanSlot.objects.create(
            week_plan=week_plan,
            day=0,
            meal_slot=self.lunch_slot,
            meal=self.private_meal,
        )

        response = self._post_grid(
            {
                (0, self.breakfast_slot.id): str(self.private_meal.id),
                (0, self.lunch_slot.id): '',
            }
        )

        self.assertRedirects(response, reverse('core:week_plan'))
        self.assertEqual(
            WeekPlanSlot.objects.get(
                week_plan=week_plan,
                day=0,
                meal_slot=self.breakfast_slot,
            ).meal,
            self.private_meal,
        )
        self.assertFalse(
            WeekPlanSlot.objects.filter(
                week_plan=week_plan,
                day=0,
                meal_slot=self.lunch_slot,
            ).exists()
        )

    def test_user_cannot_assign_another_users_private_meal(self):
        response = self._post_grid(
            {
                (0, self.breakfast_slot.id): str(self.other_private_meal.id),
            }
        )

        self.assertRedirects(response, reverse('core:week_plan'))
        week_plan = WeekPlan.objects.get(owner=self.user, week_start=monday_of_week())
        self.assertFalse(
            WeekPlanSlot.objects.filter(
                week_plan=week_plan,
                day=0,
                meal_slot=self.breakfast_slot,
            ).exists()
        )

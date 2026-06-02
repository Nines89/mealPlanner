from django.contrib import admin
from .models import (
    Ingredient, Tag, SeasonEntry,
    Meal, MealIngredient,
    MealSlot, MealSlotDefault,
    UserProfile, WeekPlan, WeekPlanSlot
)

admin.site.register(Tag)
admin.site.register(SeasonEntry)
admin.site.register(Ingredient)
admin.site.register(Meal)
admin.site.register(MealIngredient)
admin.site.register(MealSlot)
admin.site.register(MealSlotDefault)
admin.site.register(UserProfile)
admin.site.register(WeekPlan)
admin.site.register(WeekPlanSlot)
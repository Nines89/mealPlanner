from django.contrib import admin
from .models import (
    Ingredient, Tag, SeasonEntry,
    Meal, MealIngredient,
    MealSlot, MealSlotDefault,
    UserProfile, NutritionTarget, MealSlotTarget, WeekPlan, WeekPlanSlot
)


# ─────────────────────────────────────────
# TAG & STAGIONI
# ─────────────────────────────────────────

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display  = ('name', 'tag_type')
    list_filter   = ('tag_type',)
    search_fields = ('name',)


@admin.register(SeasonEntry)
class SeasonEntryAdmin(admin.ModelAdmin):
    list_display = ('name',)


# ─────────────────────────────────────────
# INGREDIENTI
# ─────────────────────────────────────────

@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display  = ('name', 'category', 'vegetable_subcategory', 'kcal', 'protein', 'carbs', 'fat')
    list_filter   = ('category', 'vegetable_subcategory', 'tags', 'seasons')
    search_fields = ('name',)
    filter_horizontal = ('tags', 'seasons')  # widget comodo per M2M


# ─────────────────────────────────────────
# MEAL
# ─────────────────────────────────────────

class MealIngredientInline(admin.TabularInline):
    model  = MealIngredient
    extra  = 1  # righe vuote precompilate
    fields = ('ingredient', 'grams')


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'owner', 'is_system')
    list_filter   = ('is_system',)
    search_fields = ('name',)
    inlines       = [MealIngredientInline]


@admin.register(MealIngredient)
class MealIngredientAdmin(admin.ModelAdmin):
    list_display  = ('meal', 'ingredient', 'grams')
    list_filter   = ('meal',)
    search_fields = ('meal__name', 'ingredient__name')


# ─────────────────────────────────────────
# SLOT PASTO
# ─────────────────────────────────────────

@admin.register(MealSlotDefault)
class MealSlotDefaultAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    ordering     = ('order',)


@admin.register(MealSlot)
class MealSlotAdmin(admin.ModelAdmin):
    list_display  = ('user', 'name', 'order')
    list_filter   = ('user',)
    ordering      = ('user', 'order')


# ─────────────────────────────────────────
# PROFILO UTENTE
# ─────────────────────────────────────────

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'allergies')
    search_fields = ('user__username',)

# ─────────────────────────────────────────
# PIANO SETTIMANALE
# ─────────────────────────────────────────

class WeekPlanSlotInline(admin.TabularInline):
    model  = WeekPlanSlot
    extra  = 0
    fields = ('day', 'meal_slot', 'meal')


@admin.register(WeekPlan)
class WeekPlanAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'owner', 'is_system', 'week_start', 'nutrition_target', 'created_at')
    list_filter   = ('is_system',)
    ordering      = ('-created_at',)
    inlines       = [WeekPlanSlotInline]


@admin.register(WeekPlanSlot)
class WeekPlanSlotAdmin(admin.ModelAdmin):
    list_display  = ('week_plan', 'day', 'meal_slot', 'meal')
    list_filter   = ('day', 'meal_slot')


# ─────────────────────────────────────────
# TARGET NUTRIZIONALE
# ─────────────────────────────────────────

class MealSlotTargetInline(admin.TabularInline):
    model   = MealSlotTarget
    extra   = 0
    fields  = ('meal_slot', 'percentage', 'kcal', 'protein', 'carbs', 'fat')


@admin.register(NutritionTarget)
class NutritionTargetAdmin(admin.ModelAdmin):
    list_display  = ('name', 'owner', 'is_system', 'target_kcal', 'diet_style', 'created_at')
    list_filter   = ('is_system', 'diet_style')
    search_fields = ('name', 'owner__username')
    readonly_fields = ('created_at',)
    inlines       = [MealSlotTargetInline]


@admin.register(MealSlotTarget)
class MealSlotTargetAdmin(admin.ModelAdmin):
    list_display  = ('nutrition_target', 'meal_slot', 'percentage', 'kcal', 'protein', 'carbs', 'fat')
    list_filter   = ('nutrition_target',)
    search_fields = ('nutrition_target__name', 'meal_slot__name')
from django.contrib import admin
from .models import (
    Ingredient, Tag, SeasonEntry,
    Meal, MealIngredient,
    MealSlot, MealSlotDefault,
    Household, HouseholdMember,
    DayKind, DayProfile, WeekPlanDayKind,
    UserProfile, NutritionTarget, MealSlotTarget, WeekPlan, WeekPlanSlot,
)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'tag_type')
    list_filter = ('tag_type',)
    search_fields = ('name',)


@admin.register(SeasonEntry)
class SeasonEntryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'vegetable_subcategory', 'kcal', 'protein', 'carbs', 'fat')
    list_filter = ('category', 'vegetable_subcategory', 'tags', 'seasons')
    search_fields = ('name',)
    filter_horizontal = ('tags', 'seasons')


class MealIngredientInline(admin.TabularInline):
    model = MealIngredient
    extra = 1
    fields = ('ingredient', 'grams')


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'genre', 'owner', 'is_system')
    list_filter = ('genre', 'is_system')
    search_fields = ('name',)
    inlines = [MealIngredientInline]


@admin.register(MealIngredient)
class MealIngredientAdmin(admin.ModelAdmin):
    list_display = ('meal', 'ingredient', 'grams')
    list_filter = ('meal',)
    search_fields = ('meal__name', 'ingredient__name')


@admin.register(MealSlotDefault)
class MealSlotDefaultAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    ordering = ('order',)


@admin.register(MealSlot)
class MealSlotAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'order')
    list_filter = ('user',)
    ordering = ('user', 'order')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'nutrition_target', 'allergies')
    search_fields = ('user__username',)


class HouseholdMemberInline(admin.TabularInline):
    model = HouseholdMember
    extra = 0
    fields = ('display_name', 'sort_order')


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'owner', 'created_at')
    search_fields = ('name', 'owner__username')
    readonly_fields = ('created_at',)
    inlines = [HouseholdMemberInline]


@admin.register(DayProfile)
class DayProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'order')
    list_filter = ('owner',)
    search_fields = ('name', 'owner__username')
    ordering = ('owner', 'order', 'id')


class WeekPlanDayKindInline(admin.TabularInline):
    model = WeekPlanDayKind
    extra = 0
    fields = ('day', 'kind')


class WeekPlanSlotInline(admin.TabularInline):
    model = WeekPlanSlot
    extra = 0
    fields = ('day', 'meal_slot', 'genre', 'meal')


@admin.register(WeekPlan)
class WeekPlanAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'owner', 'is_system', 'week_start', 'nutrition_target', 'created_at')
    list_filter = ('is_system',)
    ordering = ('-created_at',)
    inlines = [WeekPlanDayKindInline, WeekPlanSlotInline]


@admin.register(WeekPlanSlot)
class WeekPlanSlotAdmin(admin.ModelAdmin):
    list_display = ('week_plan', 'day', 'meal_slot', 'genre', 'meal')
    list_filter = ('day', 'meal_slot')


class MealSlotTargetInline(admin.TabularInline):
    model = MealSlotTarget
    extra = 0
    fields = ('meal_slot', 'percentage', 'kcal', 'protein', 'carbs', 'fat')


@admin.register(NutritionTarget)
class NutritionTargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'target_kcal', 'protein_pct_min', 'protein_pct_max', 'diet_style')
    list_filter = ('kind', 'diet_style')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'is_system', 'target_protein', 'target_carbs', 'target_fat')
    inlines = [MealSlotTargetInline]
    fieldsets = (
        (None, {
            'fields': ('kind', 'name', 'target_kcal', 'diet_style'),
        }),
        ('Macro % ranges', {
            'fields': (
                ('protein_pct_min', 'protein_pct_max'),
                ('fat_pct_min', 'fat_pct_max'),
                ('carbs_pct_min', 'carbs_pct_max'),
            ),
        }),
        ('Grams used by Fill (midpoints, read-only)', {
            'fields': ('target_protein', 'target_carbs', 'target_fat', 'is_system', 'created_at'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.append('kind')
        return readonly

    def has_add_permission(self, request):
        existing = NutritionTarget.objects.filter(kind__in=[DayKind.ON, DayKind.OFF]).count()
        return existing < 2

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.kind in (DayKind.ON, DayKind.OFF):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(MealSlotTarget)
class MealSlotTargetAdmin(admin.ModelAdmin):
    list_display = ('nutrition_target', 'meal_slot', 'percentage', 'kcal', 'protein', 'carbs', 'fat')
    list_filter = ('nutrition_target',)
    search_fields = ('nutrition_target__name', 'meal_slot__name')

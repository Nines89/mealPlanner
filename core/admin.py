from django.contrib import admin
from .models import (
    Ingredient, Tag, SeasonEntry,
    Meal, MealIngredient, MealIngredientMemberPortion,
    MealSlot, MealSlotDefault,
    Household, HouseholdMember,
    DayProfile, WeekPlanDayKind,
    UserProfile, NutritionTarget, MealSlotTarget, WeekPlan, WeekPlanSlot, WeekPlanSlotAttendance,
    DayProfileMemberModifier,
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


class MealIngredientMemberPortionInline(admin.TabularInline):
    model = MealIngredientMemberPortion
    extra = 0
    verbose_name = 'Porzione membro'
    verbose_name_plural = 'Porzioni per commensale'

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        meal_ingredient = obj

        class PortionForm(formset_class.form):
            def __init__(self, *args, **form_kw):
                super().__init__(*args, **form_kw)
                if meal_ingredient and getattr(meal_ingredient.meal, 'owner_id', None):
                    self.fields['household_member'].queryset = HouseholdMember.objects.filter(
                        household__owner=meal_ingredient.meal.owner
                    ).order_by('sort_order', 'id')
                else:
                    self.fields['household_member'].queryset = HouseholdMember.objects.none()

        formset_class.form = PortionForm
        return formset_class


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'owner', 'is_system')
    list_filter   = ('is_system',)
    search_fields = ('name',)
    inlines       = [MealIngredientInline]


@admin.register(MealIngredient)
class MealIngredientAdmin(admin.ModelAdmin):
    list_display = ('meal', 'ingredient', 'grams')
    list_filter = ('meal',)
    search_fields = ('meal__name', 'ingredient__name')
    inlines = [MealIngredientMemberPortionInline]


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
# NUCLEO FAMIGLIA
# ─────────────────────────────────────────

class HouseholdMemberInline(admin.TabularInline):
    model = HouseholdMember
    extra = 0
    fields = ('display_name', 'linked_user', 'sort_order', 'nutrition_target')

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        household = obj
        owner = household.owner if household else None

        class MemberForm(formset_class.form):
            def __init__(self, *args, **form_kw):
                super().__init__(*args, **form_kw)
                if owner:
                    self.fields['nutrition_target'].queryset = NutritionTarget.objects.filter(
                        owner=owner, is_system=False
                    ).order_by('-created_at')
                else:
                    self.fields['nutrition_target'].queryset = NutritionTarget.objects.none()

        formset_class.form = MemberForm
        return formset_class


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'owner', 'created_at')
    search_fields = ('name', 'owner__username')
    readonly_fields = ('created_at',)
    inlines = [HouseholdMemberInline]


class DayProfileMemberModifierInline(admin.TabularInline):
    model = DayProfileMemberModifier
    extra = 0
    fields = ('household_member', 'kcal_factor', 'protein_factor', 'carbs_factor', 'fat_factor')

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        day_profile = obj
        owner = day_profile.owner if day_profile else None

        class ModifierForm(formset_class.form):
            def __init__(self, *args, **form_kw):
                super().__init__(*args, **form_kw)
                if owner:
                    self.fields['household_member'].queryset = HouseholdMember.objects.filter(
                        household__owner=owner
                    ).order_by('sort_order', 'id')
                else:
                    self.fields['household_member'].queryset = HouseholdMember.objects.none()

        formset_class.form = ModifierForm
        return formset_class


@admin.register(DayProfile)
class DayProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'order')
    list_filter = ('owner',)
    search_fields = ('name', 'owner__username')
    ordering = ('owner', 'order', 'id')
    inlines = [DayProfileMemberModifierInline]


@admin.register(DayProfileMemberModifier)
class DayProfileMemberModifierAdmin(admin.ModelAdmin):
    list_display = (
        'day_profile', 'household_member',
        'kcal_factor', 'protein_factor', 'carbs_factor', 'fat_factor',
    )
    list_filter = ('day_profile__owner', 'day_profile')
    search_fields = ('day_profile__name', 'household_member__display_name')

# ─────────────────────────────────────────
# PIANO SETTIMANALE
# ─────────────────────────────────────────

class WeekPlanDayKindInline(admin.TabularInline):
    model = WeekPlanDayKind
    extra = 0
    fields = ('day', 'day_profile')

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        owner = obj.owner if obj else None

        class DayKindForm(formset_class.form):
            def __init__(self, *args, **form_kw):
                super().__init__(*args, **form_kw)
                if owner:
                    self.fields['day_profile'].queryset = DayProfile.objects.filter(owner=owner).order_by(
                        'order', 'id'
                    )
                else:
                    self.fields['day_profile'].queryset = DayProfile.objects.none()

        formset_class.form = DayKindForm
        return formset_class


class WeekPlanSlotInline(admin.TabularInline):
    model  = WeekPlanSlot
    extra  = 0
    fields = ('day', 'meal_slot', 'meal')


@admin.register(WeekPlan)
class WeekPlanAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'owner', 'is_system', 'week_start', 'nutrition_target', 'created_at')
    list_filter   = ('is_system',)
    ordering      = ('-created_at',)
    inlines       = [WeekPlanDayKindInline, WeekPlanSlotInline]


class WeekPlanSlotAttendanceInline(admin.TabularInline):
    model = WeekPlanSlotAttendance
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        slot = obj

        class AttendanceForm(formset_class.form):
            def __init__(self, *args, **form_kw):
                super().__init__(*args, **form_kw)
                owner = None
                if slot and getattr(slot, 'week_plan_id', None):
                    owner = slot.week_plan.owner
                if owner:
                    self.fields['household_member'].queryset = HouseholdMember.objects.filter(
                        household__owner=owner
                    ).order_by('sort_order', 'id')
                else:
                    self.fields['household_member'].queryset = HouseholdMember.objects.none()

        formset_class.form = AttendanceForm
        return formset_class


@admin.register(WeekPlanSlot)
class WeekPlanSlotAdmin(admin.ModelAdmin):
    list_display = ('week_plan', 'day', 'meal_slot', 'meal')
    list_filter = ('day', 'meal_slot')
    inlines = [WeekPlanSlotAttendanceInline]


# ─────────────────────────────────────────
# TARGET NUTRIZIONALE
# ─────────────────────────────────────────

class MealSlotTargetInline(admin.TabularInline):
    model   = MealSlotTarget
    extra   = 0
    fields  = ('meal_slot', 'percentage', 'kcal', 'protein', 'carbs', 'fat')


@admin.register(NutritionTarget)
class NutritionTargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'linked_members_display', 'is_system', 'target_kcal', 'diet_style', 'created_at')
    list_filter = ('is_system', 'diet_style')
    search_fields = ('name', 'owner__username', 'linked_household_members__display_name')
    readonly_fields = ('created_at',)
    inlines = [MealSlotTargetInline]

    @admin.display(description='Commensali')
    def linked_members_display(self, obj):
        names = list(
            obj.linked_household_members.order_by('sort_order', 'id').values_list('display_name', flat=True)[:8]
        )
        if not names:
            return '—'
        return ', '.join(names)


@admin.register(MealSlotTarget)
class MealSlotTargetAdmin(admin.ModelAdmin):
    list_display  = ('nutrition_target', 'meal_slot', 'percentage', 'kcal', 'protein', 'carbs', 'fat')
    list_filter   = ('nutrition_target',)
    search_fields = ('nutrition_target__name', 'meal_slot__name')
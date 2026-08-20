from django.db import models
from django.db.models import Max
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


# ─────────────────────────────────────────
# MEAL SLOTS
# ─────────────────────────────────────────

class MealSlotDefault(models.Model):
    """Global day structure: lunch and dinner only."""
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name


class MealSlot(models.Model):
    """Per-user day structure (lunch and dinner)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meal_slots')
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['order']
        unique_together = [('user', 'order')]

    def __str__(self):
        return f"{self.user.username} — {self.name}"


# ─────────────────────────────────────────
# USER PROFILE
# ─────────────────────────────────────────

class DietStyle(models.TextChoices):
    NONE        = 'none',         'None'
    VEGETARIAN  = 'vegetarian',   'Vegetarian'
    VEGAN       = 'vegan',        'Vegan'
    PESCATARIAN = 'pescatarian',  'Pescatarian'


class DayKind(models.TextChoices):
    ON = 'on', 'ON'
    OFF = 'off', 'OFF'


class UserProfile(models.Model):
    """Extends User with lasting preferences (not tied to a given week)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    allergies = models.TextField(blank=True, help_text='Free text, e.g. gluten, lactose')
    nutrition_target = models.ForeignKey(
        'NutritionTarget',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_for_profiles',
        help_text='Active household nutrition target (one plate, one target).',
    )

    def __str__(self):
        return f"Profile of {self.user.username}"


# ─────────────────────────────────────────
# HOUSEHOLD (names only; same plate for everyone)
# ─────────────────────────────────────────

class Household(models.Model):
    """Household managed by the planner (one per user). Names only; everyone eats the same plate."""
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='household_managed')
    name = models.CharField(max_length=100, blank=True, help_text='e.g. Rossi household')
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def ensure_for_user(cls, user):
        """Create household and a default member if missing (username as display name)."""
        h, _ = cls.objects.get_or_create(owner=user, defaults={'name': ''})
        if not h.members.exists():
            HouseholdMember.objects.create(
                household=h,
                display_name=user.get_username() or 'Me',
                sort_order=0,
            )
        return h

    def member_count(self):
        return self.members.count()

    def add_named_member(self, display_name):
        name = (display_name or '').strip()
        if not name:
            return None
        max_order = self.members.aggregate(highest=Max('sort_order'))['highest']
        next_order = -1 if max_order is None else max_order
        return HouseholdMember.objects.create(
            household=self,
            display_name=name,
            sort_order=next_order + 1,
        )

    def try_remove_member(self, member_id):
        if self.members.count() <= 1:
            return 'last_member'
        deleted, _counts = self.members.filter(id=member_id).delete()
        if deleted:
            return 'removed'
        return 'not_found'

    def __str__(self):
        return self.name or f"{self.owner.username}'s household"


class HouseholdMember(models.Model):
    """Household member. Same meal and grams as everyone else; count is used for shopping."""
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='members')
    display_name = models.CharField(max_length=80)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.display_name} ({self.household})"


# ─────────────────────────────────────────
# NUTRITION TARGET (ON / OFF)
# ─────────────────────────────────────────

class NutritionTarget(models.Model):
    """
    Household nutrition target. Only two rows exist: ON (training) and OFF (rest).
    Macro fields in grams are midpoints of the percentage ranges, used by the filler.
    """
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='nutrition_targets')
    is_system = models.BooleanField(default=False)
    kind = models.CharField(
        max_length=8,
        choices=DayKind.choices,
        unique=True,
        null=True,
        blank=True,
        help_text='ON or OFF day. Only these two targets are used.',
    )
    name = models.CharField(max_length=100, help_text='ON or OFF')

    target_kcal = models.PositiveIntegerField(default=2000)
    target_protein = models.PositiveIntegerField(default=150, help_text='grams (midpoint of the protein % range)')
    target_carbs = models.PositiveIntegerField(default=200, help_text='grams (midpoint of the carb % range)')
    target_fat = models.PositiveIntegerField(default=70, help_text='grams (midpoint of the fat % range)')

    protein_pct_min = models.PositiveSmallIntegerField(default=15)
    protein_pct_max = models.PositiveSmallIntegerField(default=25)
    carbs_pct_min = models.PositiveSmallIntegerField(default=45)
    carbs_pct_max = models.PositiveSmallIntegerField(default=50)
    fat_pct_min = models.PositiveSmallIntegerField(default=20)
    fat_pct_max = models.PositiveSmallIntegerField(default=25)

    diet_style = models.CharField(
        max_length=20,
        choices=DietStyle.choices,
        default=DietStyle.NONE
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def save(self, *args, **kwargs):
        if self.kind:
            from .targets import apply_midpoint_grams

            apply_midpoint_grams(self)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.target_kcal} kcal)"


# ─────────────────────────────────────────
# TAGS (diet styles / allergens)
# ─────────────────────────────────────────

class TagType(models.TextChoices):
    DIET     = 'diet',     'Diet'
    ALLERGEN = 'allergen', 'Allergen'

class Tag(models.Model):
    """
    Label that can be attached to an ingredient.
    Examples: vegan, vegetarian, gluten, lactose, nuts.
    """
    name     = models.CharField(max_length=50, unique=True)
    tag_type = models.CharField(max_length=20, choices=TagType.choices)

    def __str__(self):
        return f"{self.name} ({self.get_tag_type_display()})"


# ─────────────────────────────────────────
# SLOT SHARE OF A NUTRITION TARGET
# ─────────────────────────────────────────

class MealSlotTarget(models.Model):
    """
    Share of a NutritionTarget for one meal slot.
    Only used for personal targets (nutrition_target.owner != None).
    """
    nutrition_target = models.ForeignKey(
        NutritionTarget,
        on_delete=models.CASCADE,
        related_name='slot_targets'
    )
    meal_slot = models.ForeignKey(
        MealSlot,
        on_delete=models.CASCADE,
        related_name='slot_targets'
    )

    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text='% of the daily total (0-100)'
    )

    kcal    = models.PositiveIntegerField(null=True, blank=True)
    protein = models.PositiveIntegerField(null=True, blank=True, help_text='grams')
    carbs   = models.PositiveIntegerField(null=True, blank=True, help_text='grammi')
    fat     = models.PositiveIntegerField(null=True, blank=True, help_text='grammi')

    class Meta:
        unique_together = [('nutrition_target', 'meal_slot')]

    def __str__(self):
        return f"{self.nutrition_target.name} — {self.meal_slot.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.nutrition_target_id is None or self.meal_slot_id is None:
            return
        nt = self.nutrition_target
        ms = self.meal_slot
        if nt.owner_id is None:
            raise ValidationError(
                {
                    'nutrition_target': (
                        'Slot distribution applies only to personal targets '
                        '(with an owner user).'
                    ),
                }
            )
        if ms.user_id != nt.owner_id:
            raise ValidationError(
                {
                    'meal_slot': (
                        'The meal slot must belong to the same user as the nutrition target.'
                    ),
                }
            )

    def calculate_from_percentage(self):
        """Fill absolute values from the percentage and the parent NutritionTarget."""
        if self.percentage is None:
            return
        ratio = self.percentage / 100
        nt = self.nutrition_target
        self.kcal    = round(nt.target_kcal    * ratio)
        self.protein = round(nt.target_protein * ratio)
        self.carbs   = round(nt.target_carbs   * ratio)
        self.fat     = round(nt.target_fat     * ratio)


# ─────────────────────────────────────────
# SEASONALITY
# ─────────────────────────────────────────

class Season(models.TextChoices):
    SPRING = 'spring', 'Spring'
    SUMMER = 'summer', 'Summer'
    AUTUMN = 'autumn', 'Autumn'
    WINTER = 'winter', 'Winter'


class SeasonEntry(models.Model):
    """
    Simple table of the four seasons.
    Separate from TextChoices so Ingredient can use an M2M relation.
    """
    name = models.CharField(max_length=10, choices=Season.choices, unique=True)

    def __str__(self):
        return self.get_name_display()


# ─────────────────────────────────────────
# INGREDIENTS
# ─────────────────────────────────────────

class IngredientCategory(models.TextChoices):
    PROTEIN   = 'protein',   'Protein'
    VEGETABLE = 'vegetable', 'Vegetable'
    CARB      = 'carb',      'Carbohydrate'
    FAT       = 'fat',       'Fat'
    DAIRY     = 'dairy',     'Dairy'
    FRUIT     = 'fruit',     'Fruit'
    OTHER     = 'other',     'Other'


class VegetableSubcategory(models.TextChoices):
    LEAFY    = 'leafy',    'Leafy greens'
    ROOT     = 'root',     'Roots'
    TUBER    = 'tuber',    'Tubers'
    FLOWER   = 'flower',   'Flower vegetables'
    FRUIT_VEG = 'fruit_veg', 'Fruit vegetables'
    BULB     = 'bulb',     'Bulbs'
    STEM     = 'stem',     'Stem vegetables'
    LEGUME   = 'legume',   'Legumes'


class Ingredient(models.Model):
    """
    Ingredient with nutrition values per 100 g.
    System data: seeded by staff, not by household users.
    """
    # Identificazione
    name     = models.CharField(max_length=100, unique=True)
    category = models.CharField(
        max_length=20,
        choices=IngredientCategory.choices,
        default=IngredientCategory.OTHER
    )
    # Attivo solo se category == 'vegetable'
    vegetable_subcategory = models.CharField(
        max_length=20,
        choices=VegetableSubcategory.choices,
        blank=True,
        default=''
    )

    # Valori per 100g — macro
    kcal    = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    protein = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    carbs   = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    fat     = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])

    # Valori per 100g — dettaglio
    fiber           = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    sugars          = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    saturated_fat   = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    salt            = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    # Relazioni
    tags    = models.ManyToManyField(Tag, blank=True, related_name='ingredients')
    seasons = models.ManyToManyField(SeasonEntry, blank=True, related_name='ingredients')

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def clean(self):
        """Keep vegetable_subcategory only when category is vegetable."""
        from django.core.exceptions import ValidationError
        if self.category != IngredientCategory.VEGETABLE and self.vegetable_subcategory:
            raise ValidationError(
                'vegetable_subcategory can be set only when category is "vegetable".'
            )

# ─────────────────────────────────────────
# MEAL
# ─────────────────────────────────────────

class MealGenre(models.TextChoices):
    PASTA_CEREALI = 'pasta_cereali', 'Pasta / Cereali'
    POLLO_TACCHINO = 'pollo_tacchino', 'Pollo / Tacchino'
    PESCE = 'pesce', 'Pesce'
    CARNI_ROSSE = 'carni_rosse', 'Carni rosse'
    INSACCATI = 'insaccati', 'Insaccati'
    UOVA = 'uova', 'Uova'
    LEGUMI = 'legumi', 'Legumi'
    VERDURA = 'verdura', 'Verdura'
    FORMAGGIO = 'formaggio', 'Formaggio'
    ZUPPE = 'zuppe', 'Zuppe'
    INSALATE = 'insalate', 'Insalate'
    PIADINE = 'piadine', 'Piadine'


class Meal(models.Model):
    owner       = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='meals')
    is_system   = models.BooleanField(default=False)
    name        = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    genre = models.CharField(
        max_length=32,
        choices=MealGenre.choices,
        blank=True,
        default='',
        help_text='Household recipe group (Pasta / Pollo / Pesce / …).',
    )
    ingredients = models.ManyToManyField(Ingredient, through='MealIngredient')

    def __str__(self):
        prefix = '[SYS] ' if self.is_system else ''
        return f"{prefix}{self.name}"


class MealIngredient(models.Model):
    """Meal ↔ Ingredient: grams for one shared plate."""
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='meal_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='meal_ingredients')
    grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        validators=[MinValueValidator(0)],
        help_text='Grams on the shared plate (same for every household member).',
    )

    class Meta:
        unique_together = [('meal', 'ingredient')]

    def __str__(self):
        return f"{self.meal.name} — {self.ingredient.name} {self.grams}g"


# ─────────────────────────────────────────
# WEEK PLAN
# ─────────────────────────────────────────

class WeekPlan(models.Model):
    owner            = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='week_plans')
    is_system        = models.BooleanField(default=False)
    name             = models.CharField(max_length=100, blank=True, help_text='Plan name, e.g. "High-protein 2000 kcal"')
    week_start       = models.DateField(null=True, blank=True, help_text='Monday of the week — null for template plans')
    nutrition_target = models.ForeignKey(NutritionTarget, null=True, blank=True, on_delete=models.SET_NULL, related_name='week_plans')
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('owner', 'week_start'),
                condition=models.Q(owner__isnull=False, week_start__isnull=False),
                name='core_weekplan_owner_week_start_uniq',
            ),
        ]

    def __str__(self):
        if self.is_system:
            return f"[SYS] {self.name}"
        owner_label = self.owner.username if self.owner else '—'
        return f"{owner_label} — week of {self.week_start}"


class WeekDay(models.IntegerChoices):
    MONDAY    = 0, 'Monday'
    TUESDAY   = 1, 'Tuesday'
    WEDNESDAY = 2, 'Wednesday'
    THURSDAY  = 3, 'Thursday'
    FRIDAY    = 4, 'Friday'
    SATURDAY  = 5, 'Saturday'
    SUNDAY    = 6, 'Sunday'


class DayProfile(models.Model):
    """
    Day type defined by the planner (e.g. Training, Rest). Unused; ON/OFF lives on WeekPlanDayKind.
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='day_profiles')
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(
        max_length=240,
        blank=True,
        help_text='Optional reminder (e.g. more carbs after a workout).',
    )

    class Meta:
        ordering = ['order', 'id']
        unique_together = [('owner', 'name')]

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class WeekPlanDayKind(models.Model):
    """ON or OFF for one weekday of a week plan."""
    week_plan = models.ForeignKey(WeekPlan, on_delete=models.CASCADE, related_name='day_kinds')
    day = models.IntegerField(choices=WeekDay.choices)
    kind = models.CharField(
        max_length=8,
        choices=DayKind.choices,
        default=DayKind.OFF,
    )
    day_profile = models.ForeignKey(
        DayProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='week_plan_day_assignments',
        help_text='Unused; kept for old rows.',
    )

    class Meta:
        unique_together = [('week_plan', 'day')]

    def __str__(self):
        label = WeekDay(self.day).label
        return f"{self.week_plan} — {label}: {self.get_kind_display()}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.day_profile_id and self.week_plan.owner_id != self.day_profile.owner_id:
            raise ValidationError(
                {'day_profile': 'The day type must belong to the same planner as the week plan.'}
            )


class WeekPlanSlot(models.Model):
    """One cell of the week plan: weekday × meal slot × category, optional dish."""
    week_plan = models.ForeignKey(WeekPlan, on_delete=models.CASCADE, related_name='slots')
    day       = models.IntegerField(choices=WeekDay.choices)
    meal_slot = models.ForeignKey(MealSlot, on_delete=models.PROTECT, related_name='slots')
    genre = models.CharField(
        max_length=32,
        choices=MealGenre.choices,
        blank=True,
        default='',
        help_text='Recipe category chosen first (Soups, Fish, …).',
    )
    meal = models.ForeignKey(
        Meal,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='slots',
        help_text='Specific dish; optional until a recipe is chosen or Fill runs.',
    )

    class Meta:
        unique_together = [('week_plan', 'day', 'meal_slot')]

    def __str__(self):
        return f"{self.week_plan} — {self.get_day_display()} — {self.meal_slot.name}"


from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


# ─────────────────────────────────────────
# SLOT PASTO
# ─────────────────────────────────────────

class MealSlotDefault(models.Model):
    """Struttura giornata globale (Colazione, Pranzo, Cena)."""
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name


class MealSlot(models.Model):
    """Struttura giornata personalizzata per utente."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meal_slots')
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['order']
        unique_together = [('user', 'order')]  # niente slot con stesso ordine per utente

    def __str__(self):
        return f"{self.user.username} — {self.name}"


# ─────────────────────────────────────────
# PROFILO UTENTE
# ─────────────────────────────────────────

class DietStyle(models.TextChoices):
    NONE        = 'none',         'Nessuno'
    VEGETARIAN  = 'vegetarian',   'Vegetariano'
    VEGAN       = 'vegan',        'Vegano'
    PESCATARIAN = 'pescatarian',  'Pescatariano'


class UserProfile(models.Model):
    """Estende User con preferenze permanenti (non legate al periodo)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    allergies = models.TextField(blank=True, help_text='Testo libero, es: glutine, lattosio')

    def __str__(self):
        return f"Profilo di {self.user.username}"


# ─────────────────────────────────────────
# NUCLEO FAMIGLIA (porzioni per persona, presenza agli slot)
# ─────────────────────────────────────────

class Household(models.Model):
    """Nucleo familiare gestito dal planner (un nucleo per utente in questa versione)."""
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='household_managed')
    name = models.CharField(max_length=100, blank=True, help_text='Es. Famiglia Rossi')
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def ensure_for_user(cls, user):
        """Crea nucleo e un membro di default se mancano (es. username come nome)."""
        h, _ = cls.objects.get_or_create(owner=user, defaults={'name': ''})
        if not h.members.exists():
            HouseholdMember.objects.create(
                household=h,
                display_name=user.get_username() or 'Io',
                sort_order=0,
            )
        return h

    def __str__(self):
        return self.name or f"Nucleo di {self.owner.username}"


class HouseholdMember(models.Model):
    """Commensale: stesso pasto, grammi diversi per ingrediente (vedi MealIngredientMemberPortion)."""
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name='members')
    display_name = models.CharField(max_length=80)
    linked_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='household_memberships',
        help_text='Opzionale: collegamento a un account (futuro).',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    nutrition_target = models.ForeignKey(
        'NutritionTarget',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='linked_household_members',
        help_text='Target attivo per questo commensale; più persone possono condividere lo stesso target.',
    )

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.display_name} ({self.household})"


# ─────────────────────────────────────────
# TARGET NUTRIZIONALE (per piano)
# ─────────────────────────────────────────

class NutritionTarget(models.Model):
    """
    Target nutrizionale + stile dietetico.

    ``owner`` = planner (utente Django). I commensali referenziano il target con
    ``HouseholdMember.nutrition_target``; più membri possono condividere lo stesso target.
    """
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='nutrition_targets')
    is_system = models.BooleanField(default=False)
    name = models.CharField(max_length=100, help_text='es. "Bulk 2800kcal", "Definizione vegana"')

    target_kcal = models.PositiveIntegerField(default=2000)
    target_protein = models.PositiveIntegerField(default=150, help_text='grammi')
    target_carbs = models.PositiveIntegerField(default=200, help_text='grammi')
    target_fat = models.PositiveIntegerField(default=70, help_text='grammi')

    diet_style = models.CharField(
        max_length=20,
        choices=DietStyle.choices,
        default=DietStyle.NONE
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        prefix = '[SYS] ' if self.is_system else ''
        return f"{prefix}{self.name}"
# ─────────────────────────────────────────
# TAG (regimi speciali / allergeni)
# ─────────────────────────────────────────

class TagType(models.TextChoices):
    DIET     = 'diet',     'Regime alimentare'
    ALLERGEN = 'allergen', 'Allergene'

class Tag(models.Model):
    """
    Etichetta associabile a un ingrediente.
    Esempi: vegano, vegetariano, glutine, lattosio, frutta a guscio.
    """
    name     = models.CharField(max_length=50, unique=True)
    tag_type = models.CharField(max_length=20, choices=TagType.choices)

    def __str__(self):
        return f"{self.name} ({self.get_tag_type_display()})"


# ─────────────────────────────────────────
# DISTRIBUZIONE TARGET PER SLOT PASTO
# ─────────────────────────────────────────

class MealSlotTarget(models.Model):
    """
    Distribuzione del NutritionTarget per slot pasto.
    Esiste solo per target personali (nutrition_target.owner != None).
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
        help_text='% del totale giornaliero (0-100)'
    )

    kcal    = models.PositiveIntegerField(null=True, blank=True)
    protein = models.PositiveIntegerField(null=True, blank=True, help_text='grammi')
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
                        'La distribuzione per slot si applica solo a target personali '
                        '(con utente proprietario).'
                    ),
                }
            )
        if ms.user_id != nt.owner_id:
            raise ValidationError(
                {
                    'meal_slot': (
                        'Lo slot pasto deve appartenere allo stesso utente del target nutrizionale.'
                    ),
                }
            )

    def calculate_from_percentage(self):
        """Popola i valori assoluti dalla percentuale e dal NutritionTarget padre."""
        if self.percentage is None:
            return
        ratio = self.percentage / 100
        nt = self.nutrition_target
        self.kcal    = round(nt.target_kcal    * ratio)
        self.protein = round(nt.target_protein * ratio)
        self.carbs   = round(nt.target_carbs   * ratio)
        self.fat     = round(nt.target_fat     * ratio)


# ─────────────────────────────────────────
# STAGIONALITÀ
# ─────────────────────────────────────────

class Season(models.TextChoices):
    SPRING = 'spring', 'Primavera'
    SUMMER = 'summer', 'Estate'
    AUTUMN = 'autumn', 'Autunno'
    WINTER = 'winter', 'Inverno'


class SeasonEntry(models.Model):
    """
    Tabella semplice con le 4 stagioni.
    Separata da TextChoices per permettere la relazione M:M con Ingredient.
    """
    name = models.CharField(max_length=10, choices=Season.choices, unique=True)

    def __str__(self):
        return self.get_name_display()


# ─────────────────────────────────────────
# INGREDIENTI
# ─────────────────────────────────────────

class IngredientCategory(models.TextChoices):
    PROTEIN   = 'protein',   'Proteina'
    VEGETABLE = 'vegetable', 'Verdura'
    CARB      = 'carb',      'Carboidrato'
    FAT       = 'fat',       'Grasso'
    DAIRY     = 'dairy',     'Latticino'
    FRUIT     = 'fruit',     'Frutta'
    OTHER     = 'other',     'Altro'


class VegetableSubcategory(models.TextChoices):
    LEAFY    = 'leafy',    'Ortaggi a foglia'
    ROOT     = 'root',     'Radici'
    TUBER    = 'tuber',    'Tuberi'
    FLOWER   = 'flower',   'Ortaggi a fiore'
    FRUIT_VEG = 'fruit_veg', 'Ortaggi a frutto'
    BULB     = 'bulb',     'Bulbi'
    STEM     = 'stem',     'Ortaggi a fusto'
    LEGUME   = 'legume',   'Legumi'


class Ingredient(models.Model):
    """
    Ingrediente con valori nutrizionali per 100g.
    Dato di sistema: popolato da staff, non dagli utenti.
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
        """Validazione: subcategoria vegetale coerente con la categoria."""
        from django.core.exceptions import ValidationError
        if self.category != 'vegetable' and self.vegetable_subcategory:
            raise ValidationError(
                'vegetable_subcategory può essere impostato solo se category è "vegetable".'
            )

# ─────────────────────────────────────────
# MEAL
# ─────────────────────────────────────────

class Meal(models.Model):
    owner       = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='meals')
    is_system   = models.BooleanField(default=False)
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ingredients = models.ManyToManyField(Ingredient, through='MealIngredient')

    def __str__(self):
        prefix = '[SYS] ' if self.is_system else ''
        return f"{prefix}{self.name}"


class MealIngredient(models.Model):
    """Tabella ponte Meal ↔ Ingredient: quantità base di riferimento + porzioni per membro."""
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='meal_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='meal_ingredients')
    grams = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        validators=[MinValueValidator(0)],
        help_text='Porzione di riferimento (base). Per pasti famiglia: grammi effettivi per persona in MealIngredientMemberPortion.',
    )

    class Meta:
        unique_together = [('meal', 'ingredient')]  # stesso ingrediente non appare due volte

    def __str__(self):
        return f"{self.meal.name} — {self.ingredient.name} {self.grams}g"


class MealIngredientMemberPortion(models.Model):
    """Grammi di questo ingrediente per un commensale (stesso pasto, porzioni diverse)."""
    meal_ingredient = models.ForeignKey(
        MealIngredient,
        on_delete=models.CASCADE,
        related_name='member_portions',
    )
    household_member = models.ForeignKey(
        HouseholdMember,
        on_delete=models.CASCADE,
        related_name='meal_ingredient_portions',
    )
    grams = models.DecimalField(max_digits=6, decimal_places=1, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = [('meal_ingredient', 'household_member')]

    def __str__(self):
        return f"{self.meal_ingredient} → {self.household_member.display_name}: {self.grams}g"

    def clean(self):
        from django.core.exceptions import ValidationError

        meal = self.meal_ingredient.meal
        member = self.household_member
        if meal.owner_id is None:
            raise ValidationError(
                {'meal_ingredient': 'I pasti di sistema non supportano porzioni per membro.'}
            )
        if member.household.owner_id != meal.owner_id:
            raise ValidationError(
                {'household_member': 'Il membro deve appartenere al nucleo del proprietario del pasto.'}
            )


# ─────────────────────────────────────────
# PIANO SETTIMANALE
# ─────────────────────────────────────────

class WeekPlan(models.Model):
    owner            = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='week_plans')
    is_system        = models.BooleanField(default=False)
    name             = models.CharField(max_length=100, blank=True, help_text='Nome del piano, es: "Piano proteico 2000kcal"')
    week_start       = models.DateField(null=True, blank=True, help_text='Lunedì della settimana — null per piani template')
    nutrition_target = models.ForeignKey(NutritionTarget, null=True, blank=True, on_delete=models.PROTECT, related_name='week_plans')
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
        return f"{owner_label} — settimana del {self.week_start}"


class WeekDay(models.IntegerChoices):
    MONDAY    = 0, 'Lunedì'
    TUESDAY   = 1, 'Martedì'
    WEDNESDAY = 2, 'Mercoledì'
    THURSDAY  = 3, 'Giovedì'
    FRIDAY    = 4, 'Venerdì'
    SATURDAY  = 5, 'Sabato'
    SUNDAY    = 6, 'Domenica'


class DayProfile(models.Model):
    """
    Tipo di giorno definito dal planner (es. «Allenamento», «Riposo», «Lavoro notturno»).
    Usato per classificare ogni colonna del piano settimanale; in seguito potrai legare
    target nutrizionali o pasti diversi a ciascun tipo (logica applicativa separata).
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='day_profiles')
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(
        max_length=240,
        blank=True,
        help_text='Opzionale: promemoria (es. più carboidrati post-workout).',
    )

    class Meta:
        ordering = ['order', 'id']
        unique_together = [('owner', 'name')]

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class WeekPlanDayKind(models.Model):
    """Associa un giorno del piano (0=lunedì … 6=domenica) a un tipo di giorno."""
    week_plan = models.ForeignKey(WeekPlan, on_delete=models.CASCADE, related_name='day_kinds')
    day = models.IntegerField(choices=WeekDay.choices)
    day_profile = models.ForeignKey(
        DayProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='week_plan_day_assignments',
        help_text='Vuoto = giorno non etichettato.',
    )

    class Meta:
        unique_together = [('week_plan', 'day')]

    def __str__(self):
        label = WeekDay(self.day).label
        profile = self.day_profile.name if self.day_profile_id else '—'
        return f"{self.week_plan} — {label}: {profile}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.day_profile_id and self.week_plan.owner_id != self.day_profile.owner_id:
            raise ValidationError(
                {'day_profile': 'Il tipo giorno deve appartenere allo stesso planner del piano.'}
            )


class DayProfileMemberModifier(models.Model):
    """
    Fattore moltiplicativo per macro, specifico per combinazione tipo-giorno × commensale.
    Esempio: membro "Mario" in giorno "Allenamento" → kcal_factor=1.15, protein_factor=1.10.
    Assenza di riga per una combinazione = nessuna variazione (fattore 1.0 implicito in UI/calcolo).
    """
    day_profile = models.ForeignKey(
        DayProfile,
        on_delete=models.CASCADE,
        related_name='member_modifiers',
    )
    household_member = models.ForeignKey(
        HouseholdMember,
        on_delete=models.CASCADE,
        related_name='day_modifiers',
    )
    kcal_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    protein_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    carbs_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    fat_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)

    class Meta:
        unique_together = [('day_profile', 'household_member')]

    def __str__(self):
        return f"{self.day_profile.name} × {self.household_member.display_name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.day_profile_id and self.household_member_id:
            if self.day_profile.owner_id != self.household_member.household.owner_id:
                raise ValidationError(
                    'Il tipo giorno e il commensale devono appartenere allo stesso planner.'
                )
        for field_name in ('kcal_factor', 'protein_factor', 'carbs_factor', 'fat_factor'):
            value = getattr(self, field_name)
            if value is not None and value <= 0:
                raise ValidationError({field_name: 'Il fattore deve essere maggiore di zero.'})


class WeekPlanSlot(models.Model):
    """Singolo slot del piano: giorno × slot pasto × meal assegnata."""
    week_plan = models.ForeignKey(WeekPlan, on_delete=models.CASCADE, related_name='slots')
    day       = models.IntegerField(choices=WeekDay.choices)
    meal_slot = models.ForeignKey(MealSlot, on_delete=models.PROTECT, related_name='slots')
    meal      = models.ForeignKey(Meal, on_delete=models.PROTECT, related_name='slots')

    class Meta:
        unique_together = [('week_plan', 'day', 'meal_slot')]  # no duplicati

    def __str__(self):
        return f"{self.week_plan} — {self.get_day_display()} — {self.meal_slot.name}"


class WeekPlanSlotAttendance(models.Model):
    """Chi partecipa a quel pasto nello slot (per calcoli lista spesa / macro solo presenti)."""
    slot = models.ForeignKey(WeekPlanSlot, on_delete=models.CASCADE, related_name='attendances')
    household_member = models.ForeignKey(
        HouseholdMember,
        on_delete=models.CASCADE,
        related_name='slot_attendances',
    )

    class Meta:
        unique_together = [('slot', 'household_member')]

    def __str__(self):
        return f"{self.slot} — {self.household_member.display_name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        owner_id = self.slot.week_plan.owner_id
        if owner_id is None:
            raise ValidationError({'slot': 'Slot senza proprietario non supportato.'})
        if self.household_member.household.owner_id != owner_id:
            raise ValidationError(
                {'household_member': 'Il membro deve appartenere al nucleo del proprietario del piano.'}
            )


from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Ingredient, Meal, MealGenre, MealIngredient
from .planning import quantize_grams

FORM_CONTROL_CSS = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm'


class RecipeForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = ('name', 'genre')
        labels = {'name': 'Nome', 'genre': 'Categoria'}
        widgets = {
            'name': forms.TextInput(attrs={'class': FORM_CONTROL_CSS}),
            'genre': forms.Select(attrs={'class': FORM_CONTROL_CSS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Categoria obbligatoria: senza, il piatto non entra in nessun pool di build.
        self.fields['genre'].choices = MealGenre.choices
        self.fields['genre'].required = True


class RecipeIngredientForm(forms.ModelForm):
    class Meta:
        model = MealIngredient
        fields = ('ingredient', 'grams')
        widgets = {
            'ingredient': forms.Select(attrs={'class': FORM_CONTROL_CSS}),
            'grams': forms.NumberInput(attrs={'class': FORM_CONTROL_CSS, 'min': '1', 'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ingredient'].queryset = Ingredient.objects.order_by('name')

    def clean_grams(self):
        grams = self.cleaned_data.get('grams')
        if grams is None:
            return grams
        if grams <= Decimal('0'):
            raise ValidationError('Inserisci grammi maggiori di zero.')
        # Stesso arrotondamento (10 g) di seed_catalog e sync Notion, così il
        # confronto della sync non segnala differenze fittizie.
        return quantize_grams(grams)


class BaseRecipeIngredientFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            if not form.cleaned_data or self._should_delete_form(form):
                continue
            ingredient = form.cleaned_data.get('ingredient')
            if ingredient is None:
                continue
            if ingredient.id in seen:
                raise ValidationError(f'Ingrediente ripetuto: {ingredient.name}.')
            seen.add(ingredient.id)
        if not seen:
            raise ValidationError('Serve almeno un ingrediente.')


RecipeIngredientFormSet = inlineformset_factory(
    Meal,
    MealIngredient,
    form=RecipeIngredientForm,
    formset=BaseRecipeIngredientFormSet,
    extra=3,
    can_delete=True,
)

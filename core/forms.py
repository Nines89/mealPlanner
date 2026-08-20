from django import forms

from .models import Ingredient, IngredientCategory
from .planning import (
    FILL_AUTOMATIC,
    FILL_SEMI_AUTO,
    FILL_SEMI_MANUAL,
    ingredients_for_category,
)

FORM_CONTROL_CSS = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm'

_REQUIRED_BY_MODE = {
    FILL_SEMI_MANUAL: ('protein', 'vegetable'),
    FILL_SEMI_AUTO: ('protein',),
}

_FIELD_ERRORS = {
    'protein': 'Pick a protein.',
    'vegetable': 'Pick a vegetable.',
}


class AddHouseholdMemberForm(forms.Form):
    display_name = forms.CharField(
        max_length=80,
        label='Name',
        widget=forms.TextInput(attrs={'class': FORM_CONTROL_CSS}),
    )


class FillSlotForm(forms.Form):
    MODE_SEMI_MANUAL = FILL_SEMI_MANUAL
    MODE_SEMI_AUTO = FILL_SEMI_AUTO
    MODE_AUTOMATIC = FILL_AUTOMATIC
    MODE_CHOICES = (
        (FILL_SEMI_MANUAL, 'Semi-manual — pick protein and vegetable'),
        (FILL_SEMI_AUTO, 'Semi-auto — pick protein, random vegetable'),
        (FILL_AUTOMATIC, 'Automatic — random protein and vegetable'),
    )

    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        initial=FILL_SEMI_MANUAL,
        widget=forms.RadioSelect,
        label='Mode',
    )
    protein = forms.ModelChoiceField(
        queryset=Ingredient.objects.none(),
        required=False,
        label='Protein',
        widget=forms.Select(attrs={'class': FORM_CONTROL_CSS}),
    )
    vegetable = forms.ModelChoiceField(
        queryset=Ingredient.objects.none(),
        required=False,
        label='Vegetable',
        widget=forms.Select(attrs={'class': FORM_CONTROL_CSS}),
    )
    carb = forms.ModelChoiceField(
        queryset=Ingredient.objects.none(),
        required=False,
        label='Carb (optional)',
        widget=forms.Select(attrs={'class': FORM_CONTROL_CSS}),
    )
    fat = forms.ModelChoiceField(
        queryset=Ingredient.objects.none(),
        required=False,
        label='Fat / oil (optional)',
        widget=forms.Select(attrs={'class': FORM_CONTROL_CSS}),
    )

    def __init__(self, *args, diet_style=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_ingredient_querysets(diet_style)
        self.fields['protein'].empty_label = '— choose —'
        self.fields['vegetable'].empty_label = '— choose —'
        self.fields['carb'].empty_label = '— none —'
        self.fields['fat'].empty_label = '— none —'

    def _set_ingredient_querysets(self, diet_style):
        categories = {
            'protein': IngredientCategory.PROTEIN,
            'vegetable': IngredientCategory.VEGETABLE,
            'carb': IngredientCategory.CARB,
            'fat': IngredientCategory.FAT,
        }
        for field_name, category in categories.items():
            self.fields[field_name].queryset = ingredients_for_category(
                category, diet_style
            )

    def clean(self):
        cleaned = super().clean()
        required = _REQUIRED_BY_MODE.get(cleaned.get('mode'), ())
        for field_name in required:
            if not cleaned.get(field_name):
                self.add_error(field_name, _FIELD_ERRORS[field_name])
        return cleaned

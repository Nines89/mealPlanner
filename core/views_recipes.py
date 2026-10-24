from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms_recipes import RecipeForm, RecipeIngredientFormSet
from .models import MealGenre
from .week import catalog_meals_for

NO_GENRE = 'none'


def _group_by_genre(meals):
    buckets = {value: [] for value, _label in MealGenre.choices}
    uncategorized = []
    for meal in meals:
        buckets.get(meal.genre, uncategorized).append(meal)
    groups = [
        {'value': value, 'label': label, 'meals': buckets[value]}
        for value, label in MealGenre.choices
        if buckets[value]
    ]
    if uncategorized:
        groups.append({'value': NO_GENRE, 'label': 'Senza categoria', 'meals': uncategorized})
    return groups


def _protect_from_seed(meal, original_name):
    """Piatto di sistema modificato: seed_catalog non lo ricostruisce più."""
    meal.customized = True
    if not meal.seed_key:
        meal.seed_key = original_name  # nome originale, per riconoscerlo anche se rinominato
    meal.save(update_fields=['customized', 'seed_key'])


@login_required
@require_http_methods(['GET'])
def recipe_list(request):
    """Tutte le ricette visibili all'utente (sistema + proprie), per macro categoria."""
    query = request.GET.get('q', '').strip()
    meals = (
        catalog_meals_for(request.user)
        .prefetch_related('meal_ingredients__ingredient')
        .order_by('name')
    )
    if query:
        meals = meals.filter(name__icontains=query)
    meals = list(meals)
    return render(
        request,
        'core/recipe_list.html',
        {
            'groups': _group_by_genre(meals),
            'total': len(meals),
            'query': query,
            'open_genre': request.GET.get('open', ''),
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def recipe_edit(request, pk):
    """Modifica nome, categoria e ingredienti di una ricetta."""
    meal = get_object_or_404(catalog_meals_for(request.user), pk=pk)
    original_name = meal.name
    if request.method == 'POST':
        form = RecipeForm(request.POST, instance=meal)
        formset = RecipeIngredientFormSet(request.POST, instance=meal)
        if form.is_valid() and formset.is_valid():
            changed = form.has_changed() or formset.has_changed()
            with transaction.atomic():
                form.save()
                formset.save()
                if changed and meal.is_system:
                    _protect_from_seed(meal, original_name)
            messages.success(request, f'Ricetta “{meal.name}” salvata.')
            return redirect(f"{reverse('core:recipes')}?open={meal.genre or NO_GENRE}")
    else:
        form = RecipeForm(instance=meal)
        formset = RecipeIngredientFormSet(instance=meal)
    return render(
        request,
        'core/recipe_edit.html',
        {'meal': meal, 'form': form, 'formset': formset},
    )

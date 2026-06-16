from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Ingredient, Meal, WeekPlan, NutritionTarget


def get_catalog_stats_context():
    """Conteggio ingredienti e pasti di sistema (dashboard + partial HTMX)."""
    return {
        'ingredient_count': Ingredient.objects.count(),
        'meal_count': Meal.objects.filter(is_system=True).count(),
    }


def get_current_nutrition_target(user):
    """
    Ritorna il NutritionTarget da mostrare in dashboard:
    1. quello del WeekPlan della settimana corrente, se esiste
    2. altrimenti l'ultimo NutritionTarget personale creato
    3. altrimenti None
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    current_plan = WeekPlan.objects.filter(
        owner=user,
        week_start=monday
    ).select_related('nutrition_target').first()

    if current_plan and current_plan.nutrition_target:
        return current_plan.nutrition_target

    return NutritionTarget.objects.filter(owner=user).order_by('-created_at').first()


@login_required
def dashboard(request):
    context = {
        **get_catalog_stats_context(),
        'nutrition_target': get_current_nutrition_target(request.user),
    }
    return render(request, 'core/dashboard.html', context)


def register(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)          # login automatico post-registrazione
            return redirect('core:dashboard')
    else:
        form = UserCreationForm()

    return render(request, 'registration/register.html', {'form': form})


@login_required
def catalog_partial(request):
    return render(request, 'core/_catalog_section.html', get_catalog_stats_context())
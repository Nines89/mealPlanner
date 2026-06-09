from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Ingredient, Meal


@login_required
def dashboard(request):
    context = {
        'ingredient_count': Ingredient.objects.count(),
        'meal_count': Meal.objects.filter(is_system=True).count(),
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
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('piano-settimana/', views.week_plan_current, name='week_plan'),
    path(
        'piano-settimana/fill/<int:day>/<int:slot_id>/',
        views.week_plan_fill_slot,
        name='week_plan_fill',
    ),
    path('famiglia/', views.household_manage, name='household'),
    path('lista-spesa/', views.shopping_list, name='shopping_list'),
    path('target-nuovo/', views.nutrition_target_edit, name='nutrition_target_edit'),
]
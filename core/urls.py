from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('piano-settimana/', views.week_plan_current, name='week_plan'),
    path('famiglia/', views.household_manage, name='household'),
    path('tipi-giorno/', views.day_profiles_manage, name='day_profiles'),
    path('target-nuovo/', views.nutrition_target_create, name='nutrition_target_create'),
    path('register/', views.register, name='register'),
    path('catalog-partial/', views.catalog_partial, name='catalog_partial'),
]
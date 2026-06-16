from django.urls import path

from .api_views import IngredientListAPIView

urlpatterns = [
    path('ingredients/', IngredientListAPIView.as_view(), name='api-ingredient-list'),
]

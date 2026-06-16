from rest_framework import generics

from .models import Ingredient
from .serializers import IngredientSerializer


class IngredientListAPIView(generics.ListAPIView):
    """Lista ingredienti di sistema (read-only), utile per client esterni o esercizi DRF."""

    queryset = Ingredient.objects.all().order_by('name')
    serializer_class = IngredientSerializer

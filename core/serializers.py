from rest_framework import serializers

from .models import Ingredient


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = [
            'id',
            'name',
            'category',
            'vegetable_subcategory',
            'kcal',
            'protein',
            'carbs',
            'fat',
            'fiber',
            'sugars',
            'saturated_fat',
            'salt',
        ]

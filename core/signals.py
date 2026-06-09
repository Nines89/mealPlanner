from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile, MealSlot, MealSlotDefault


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Crea UserProfile e MealSlot default quando viene creato un nuovo User."""
    if not created:
        return

    # Crea il profilo
    UserProfile.objects.create(user=instance)

    # Copia i MealSlotDefault come MealSlot personali dell'utente
    for slot_default in MealSlotDefault.objects.all():
        MealSlot.objects.create(
            user=instance,
            name=slot_default.name,
            order=slot_default.order,
        )
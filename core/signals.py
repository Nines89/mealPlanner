from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile, MealSlot, MealSlotDefault


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile and copy default meal slots for a new User."""
    if not created:
        return
    UserProfile.objects.create(user=instance)
    for slot_default in MealSlotDefault.objects.all():
        MealSlot.objects.get_or_create(
            user=instance,
            order=slot_default.order,
            defaults={'name': slot_default.name},
        )

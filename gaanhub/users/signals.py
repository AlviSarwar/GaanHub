"""
Signals for the users app.
Auto-creates a UserProfile whenever a new User is created
(covers admin panel, management commands, etc. — not just the register view).
"""
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from music.models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a new User is saved."""
    if created:
        UserProfile.objects.get_or_create(user=instance)

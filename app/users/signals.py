import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from app.dashboard.models import Dashboard

logger = logging.getLogger(__name__)
User = get_user_model()

@receiver(post_save, sender=User)
def setup_new_user(instance, created, **kwargs):
    if created:
        if not hasattr(instance, "dashboard"):
            Dashboard.objects.create(user=instance)
            logger.info(f"Dashboard created for new user {instance.email}")
        else:
            logger.warning(f"Dashboard already exists for user {instance.email} (unexpected)")

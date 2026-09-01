"""
Cache invalidation on subscription/module changes.

This is the primary invalidation path referenced in middleware.py — the
Redis TTL is a backstop for cases these signals don't cover (e.g. a direct
DB edit), not the main mechanism.
"""
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from apps.core.middleware import invalidate_subscription_cache
from apps.core.models import Subscription


@receiver(post_save, sender=Subscription)
def on_subscription_saved(sender, instance: Subscription, **kwargs):
    invalidate_subscription_cache(instance.client)


@receiver(m2m_changed, sender=Subscription.extra_modules.through)
def on_extra_modules_changed(sender, instance: Subscription, **kwargs):
    invalidate_subscription_cache(instance.client)

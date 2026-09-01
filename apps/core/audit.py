"""
Append-only audit trail. `record()` is called explicitly from the JWT auth
views (SimpleJWT is stateless and fires none of Django's auth signals); the
signal receivers below cover session logins to the Django admin (superadmins).
"""
from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db import connection
from django.dispatch import receiver

from apps.core.models import AuditLog


def record(action: str, actor: str = "system", **detail) -> None:
    AuditLog.objects.create(
        schema_name=getattr(connection, "schema_name", "-"),
        actor=actor or "system",
        action=action,
        detail=detail,
    )


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    record("auth.admin_login", actor=getattr(user, "email", str(user)))


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    record("auth.admin_logout", actor=getattr(user, "email", str(user)) if user else "unknown")


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    record(
        "auth.admin_login_failed",
        actor=credentials.get("username") or credentials.get("email") or "unknown",
    )

"""
Per-tenant user. `apps.accounts` is in BOTH SHARED_APPS and TENANT_APPS:
the public-schema `accounts_user` table holds superadmins, and every tenant
schema has its own `accounts_user` table holding that institution's users.
Isolation comes from the schema — there is no tenant FK.

What a user may do is decided by `apps.org.RoleAssignment` (roles per branch,
ADR-006), not by a field here.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager


class User(AbstractUser):
    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        HINDI = "hi", "हिन्दी"

    username = None
    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    preferred_language = models.CharField(max_length=2, choices=Language.choices, default=Language.ENGLISH)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email

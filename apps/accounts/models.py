"""
Per-tenant user. `apps.accounts` is in BOTH SHARED_APPS and TENANT_APPS:
the public-schema `accounts_user` table holds superadmins, and every tenant
schema has its own `accounts_user` table holding that institution's users.
Isolation comes from the schema — there is no tenant FK.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"          # full access incl. destructive actions
        STAFF = "staff", "Staff"          # read + write
        READ_ONLY = "read_only", "Read only"  # safe methods only

    username = None
    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STAFF)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email

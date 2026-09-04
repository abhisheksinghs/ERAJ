"""HR module. TENANT_APPS. Plain records — no workflow beyond CRUD, so no
services.py (nothing here has a business rule to enforce)."""
from django.db import models
from django.utils import timezone

from apps.core.mixins import SoftDelete, TimeStamped


class Department(TimeStamped):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Employee(TimeStamped, SoftDelete):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees"
    )
    date_joined = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("full_name",)

    def __str__(self) -> str:
        return self.full_name

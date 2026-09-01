"""
Library module models. This app is in TENANT_APPS: a fresh copy of these
tables is created in EVERY tenant schema. There is deliberately NO
tenant_id/client foreign key on Book — isolation comes from the Postgres
schema itself, not an application-level filter. This is the core guarantee
schema-per-tenant buys over shared-schema+tenant_id (see docs/FAILURE_MODES.md).
"""
from django.db import models


class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    isbn = models.CharField(max_length=20, unique=True)
    copies_total = models.PositiveIntegerField(default=1)
    copies_available = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title


class Member(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.full_name


class Issue(models.Model):
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="issues")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="issues")
    issued_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.book} -> {self.member}"

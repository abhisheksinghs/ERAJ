"""
Core (public-schema) models.

These live in SHARED_APPS and are visible from every schema via django-tenants
routing rules, but they are only ever *written* from the public schema
(superadmin context). Tenant apps (library, hostel, ...) read Subscription
state via the middleware/permission layer, never by importing these models
directly into tenant-scoped business logic.
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin


class Client(TenantMixin):
    """
    A tenant. One row per client (e.g. "ABC College"). django-tenants creates
    a dedicated Postgres schema per row (see `schema_name`) and migrates
    TENANT_APPS models into it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=63, unique=True)  # also used as schema_name basis
    created_at = models.DateTimeField(auto_now_add=True)

    # Automatically create the tenant's schema when the row is saved.
    auto_create_schema = True
    auto_drop_schema = False  # never auto-drop in production; require explicit ops action

    def __str__(self) -> str:
        return self.name


class Domain(DomainMixin):
    """
    Maps a hostname (e.g. abc.library.eraj.com) to a Client schema.
    django-tenants resolves `request.tenant` from this table on every request.
    """


class Plan(models.Model):
    """A named bundle: which modules it includes, at what price."""

    name = models.CharField(max_length=100, unique=True)
    price_per_year = models.DecimalField(max_digits=10, decimal_places=2)
    is_custom = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class Module(models.Model):
    """
    A product/module (Library, Hostel, Attendance, ...). Corresponds 1:1 with
    an entry in TENANT_APPS, but stored as data so Super Admin can toggle
    access without a code deploy.
    """

    code = models.SlugField(max_length=50, unique=True)  # e.g. "library"
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class PlanModule(models.Model):
    """Which modules a given Plan includes (the pivot the doc glossed over)."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="plan_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("plan", "module")


class Subscription(models.Model):
    """
    The single source of truth for a client's access state.

    Explicit state machine (see docs/FAILURE_MODES.md, "Grace period
    ambiguity"): every module-permission check reads `status`, never infers
    it from `end_date` alone, so the transition logic lives in one place.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        GRACE_PERIOD = "grace_period", "Grace period"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField()
    grace_period_days = models.PositiveIntegerField(default=7)

    # Per-client overrides on top of the plan's modules (e.g. a custom add-on).
    extra_modules = models.ManyToManyField(Module, blank=True, related_name="extra_for")

    updated_at = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        if self.end_date <= self.start_date:
            raise ValidationError("end_date must be after start_date")

    def active_modules(self) -> set[str]:
        """Module codes this subscription currently grants, regardless of status.

        Callers MUST check `is_access_allowed()` separately — this method
        answers "what's in the plan", not "can they use it right now".
        """
        plan_codes = set(
            self.plan.plan_modules.values_list("module__code", flat=True)
        )
        extra_codes = set(self.extra_modules.values_list("code", flat=True))
        return plan_codes | extra_codes

    def is_access_allowed(self) -> bool:
        """The one place that decides "does this tenant get in at all"."""
        return self.status in (self.Status.ACTIVE, self.Status.GRACE_PERIOD)

    def granted_modules(self) -> set[str]:
        """Module codes this tenant may use *right now* — empty unless access
        is currently allowed. This is the method the middleware and permission
        layer must call; `active_modules()` answers the narrower "what's in the
        plan" question and says nothing about whether they can use it.
        """
        return self.active_modules() if self.is_access_allowed() else set()

    def recompute_status(self, *, today=None) -> str:
        """
        Deterministic transition function, called by the daily Celery beat
        task (see apps/core/tasks.py) and by tests. Kept pure (no DB writes)
        so it's trivially unit-testable without touching the database.

        TERMINATED is a manual, contractual action (a superadmin ends the
        contract) — this time-based function never auto-enters it and never
        auto-exits it.
        """
        if self.status == self.Status.TERMINATED:
            return self.Status.TERMINATED
        today = today or timezone.localdate()
        if today <= self.end_date:
            return self.Status.ACTIVE
        grace_end = self.end_date + timezone.timedelta(days=self.grace_period_days)
        if today <= grace_end:
            return self.Status.GRACE_PERIOD
        return self.Status.SUSPENDED

    def __str__(self) -> str:
        return f"{self.client.name} — {self.plan.name} ({self.status})"


class AuditLog(models.Model):
    """
    Append-only trail of security-relevant events, in the public schema so a
    single query spans every tenant. Written by signals (see apps/core/audit.py)
    and superadmin actions — never updated or deleted (no admin/API surface for
    that; enforce with a DB grant in production, Phase 3).
    """

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    schema_name = models.CharField(max_length=63, db_index=True)
    actor = models.CharField(max_length=255, blank=True)  # email, or "system"
    action = models.CharField(max_length=100, db_index=True)  # "auth.login", "subscription.status_changed", ...
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-at",)

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.schema_name} {self.action}"

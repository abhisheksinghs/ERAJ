"""Parent / student portal (ADR-011): OTP login codes, day-scholar leave, change requests."""
from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class PortalOTP(models.Model):
    """One login code. Only a salted hash is stored; 5-minute life, 5 tries."""

    phone = models.CharField(max_length=10, db_index=True, help_text="Last 10 digits")
    code_hash = models.CharField(max_length=64)
    salt = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class StudentLeave(TimeStamped, BranchOwned):
    """A day scholar's leave application, decided by the class teacher."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="portal_leaves")
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.CharField(max_length=300)
    requested_by = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.REQUESTED)
    decided_by = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-from_date", "-pk")
        constraints = [models.CheckConstraint(check=Q(to_date__gte=models.F("from_date")), name="portal_leave_dates")]


class ChangeRequest(TimeStamped, BranchOwned):
    """Address / phone / email change asked from the portal; applies only once the office approves."""

    class Field(models.TextChoices):
        ADDRESS = "address", "Address"
        PHONE = "phone", "Parent's mobile number"
        EMAIL = "email", "Parent's email"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved (applied)"
        REJECTED = "rejected", "Rejected"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="change_requests")
    guardian = models.ForeignKey("people.Guardian", null=True, blank=True, on_delete=models.SET_NULL, related_name="change_requests")
    field = models.CharField(max_length=7, choices=Field.choices)
    old_value = models.TextField(blank=True)
    new_value = models.TextField()
    requested_by = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.REQUESTED)
    decided_by = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-created_at",)

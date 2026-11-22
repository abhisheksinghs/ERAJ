"""
HR (ADR-009). Staff identity lives in the shared registry (`people.Staff`,
`people.Department`, ADR-002); HR adds the profile, documents, designations,
staff attendance and leave. Every row is branch-owned (ADR-001).
"""
from __future__ import annotations

import os
import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.mixins import SoftDelete, TimeStamped
from apps.org.models import BranchOwned

PAN = RegexValidator(r"^[A-Z]{5}[0-9]{4}[A-Z]$", "PAN must look like ABCDE1234F.")
IFSC = RegexValidator(r"^[A-Z]{4}0[A-Z0-9]{6}$", "IFSC must look like SBIN0001234.")
UAN = RegexValidator(r"^\d{12}$", "UAN is 12 digits.")
DIGITS = RegexValidator(r"^\d{6,20}$", "Digits only.")


class Designation(TimeStamped, SoftDelete, BranchOwned):
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="hr_designation_unique")]

    def __str__(self) -> str:
        return self.name


class StaffProfile(TimeStamped, BranchOwned):
    """Everything about a staff member beyond the registry row. Payroll
    identity (PAN/UAN/bank) is sensitive: readable only with hr.profile.view."""

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    staff = models.OneToOneField("people.Staff", on_delete=models.CASCADE, related_name="hr_profile")
    gender = models.CharField(max_length=6, choices=Gender.choices, blank=True)
    father_or_spouse = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    probation_end = models.DateField(null=True, blank=True)
    relieved_on = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=255, blank=True)
    # payroll identity
    pan = models.CharField("PAN", max_length=10, blank=True, validators=[PAN])
    uan = models.CharField("UAN (EPF)", max_length=12, blank=True, validators=[UAN])
    esic_ip = models.CharField("ESIC IP number", max_length=17, blank=True, validators=[DIGITS])
    pran = models.CharField("PRAN (NPS)", max_length=12, blank=True, validators=[DIGITS])
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=20, blank=True, validators=[DIGITS])
    ifsc = models.CharField("IFSC", max_length=11, blank=True, validators=[IFSC])

    def __str__(self) -> str:
        return f"Profile of {self.staff}"

    @property
    def bank_account_masked(self) -> str:
        a = self.bank_account
        return f"{'•' * max(len(a) - 4, 0)}{a[-4:]}" if a else ""


def _document_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return f"hr/documents/{instance.branch_id}/{uuid.uuid4().hex}{ext}"


class StaffDocument(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        APPOINTMENT = "appointment", "Appointment letter"
        CERTIFICATE = "certificate", "Certificate"
        ID_PROOF = "id_proof", "ID proof"
        OTHER = "other", "Other"

    staff = models.ForeignKey("people.Staff", on_delete=models.CASCADE, related_name="hr_documents")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to=_document_path)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=60, blank=True)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("staff", "-created_at")


class StaffAttendance(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LEAVE = "leave", "Leave"
        HALF_DAY = "half_day", "Half-day"
        ON_DUTY = "on_duty", "On duty"

    class Source(models.TextChoices):
        MANUAL = "manual", "Marked"
        DEVICE = "device", "Device punch"
        LEAVE = "leave", "Approved leave"

    staff = models.ForeignKey("people.Staff", on_delete=models.CASCADE, related_name="hr_attendance")
    date = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices)
    source = models.CharField(max_length=6, choices=Source.choices, default=Source.MANUAL)
    leave = models.ForeignKey("LeaveApplication", null=True, blank=True, on_delete=models.SET_NULL, related_name="attendance_days")
    unpaid = models.BooleanField(default=False, help_text="Leave without pay — counts as loss of pay")
    marked_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("date", "staff__full_name")
        constraints = [models.UniqueConstraint(fields=["staff", "date"], name="hr_one_attendance_per_day")]
        indexes = [models.Index(fields=["branch", "date"], name="hr_att_branch_date")]


class LeaveType(TimeStamped, SoftDelete, BranchOwned):
    code = models.CharField(max_length=10, help_text="CL, EL, ML, LWP …")
    name = models.CharField(max_length=60)
    name_hi = models.CharField(max_length=60, blank=True)
    annual_days = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                      help_text="Yearly entitlement; empty = no limit (e.g. leave without pay)")
    paid = models.BooleanField(default=True)
    allow_half_day = models.BooleanField(default=True)
    max_carry_forward = models.DecimalField(max_digits=5, decimal_places=1, default=0)

    class Meta:
        ordering = ("code",)
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="hr_leave_type_code_unique")]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def limited(self) -> bool:
        return self.annual_days is not None


class LeaveBalance(TimeStamped, BranchOwned):
    """Per staff, type and calendar year. Available = entitled − used − pending."""

    staff = models.ForeignKey("people.Staff", on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="balances")
    year = models.PositiveSmallIntegerField()
    entitled = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Incl. carried forward")
    used = models.DecimalField(max_digits=5, decimal_places=1, default=0)

    class Meta:
        ordering = ("staff", "leave_type__code")
        constraints = [
            models.UniqueConstraint(fields=["staff", "leave_type", "year"], name="hr_leave_balance_unique"),
            models.CheckConstraint(check=Q(used__gte=0), name="hr_leave_used_nonneg"),
        ]


class LeaveApplication(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    staff = models.ForeignKey("people.Staff", on_delete=models.CASCADE, related_name="leave_applications")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="applications")
    start = models.DateField()
    end = models.DateField()
    half_day = models.BooleanField(default=False, help_text="Only for a single-day application")
    days = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    applied_by = models.CharField(max_length=255, blank=True)
    decided_by = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-start",)
        constraints = [models.CheckConstraint(check=Q(end__gte=models.F("start")), name="hr_leave_dates")]
        indexes = [models.Index(fields=["staff", "status"], name="hr_leave_staff_status")]

    def __str__(self) -> str:
        return f"{self.staff} {self.leave_type.code} {self.start}–{self.end}"

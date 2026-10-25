"""
Fees ledger (ADR-003). One account per student:

    Charge   — something the student owes (a plan instalment, hostel month,
               mess month, bus fare, library fine, late fine, manual adjustment)
    Concession — an approved reduction; turned into Charge.discount
    Receipt  — money received, allocated to charges by ReceiptLine
    Refund   — money paid back, taken off charges by RefundLine

    outstanding(charge) = amount - discount - Σ receipt lines (live receipts)
                                            + Σ refund lines

Other modules never write these tables directly: they call
`apps.fees.services.post_charge(...)` / `cancel_future_charges(...)` inside
their own transaction. Every row is branch-owned (ADR-001).
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned

MONEY = {"max_digits": 12, "decimal_places": 2}
ZERO = Decimal("0.00")


class FeeSettings(TimeStamped, BranchOwned):
    """Per-branch fees configuration (one row per branch)."""

    receipt_prefix = models.CharField(max_length=10, default="RC", help_text='Printed as "<prefix>/<FY>/<number>"')
    cash_ledger = models.CharField(max_length=100, default="Cash", help_text="Tally ledger for cash receipts")
    bank_ledger = models.CharField(max_length=100, default="Bank", help_text="Tally ledger for non-cash receipts")
    tally_company = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name_plural = "fee settings"
        constraints = [models.UniqueConstraint(fields=["branch"], name="fees_one_settings_per_branch")]


class FeeHead(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        TUITION = "tuition", "Tuition"
        ADMISSION = "admission", "Admission"
        EXAM = "exam", "Exam"
        DEVELOPMENT = "development", "Development"
        TRANSPORT = "transport", "Transport"
        HOSTEL = "hostel", "Hostel"
        MESS = "mess", "Mess"
        LIBRARY_FINE = "library_fine", "Library fine"
        LATE_FINE = "late_fine", "Late fine"
        OTHER = "other", "Other"

    class LateFine(models.TextChoices):
        NONE = "none", "No late fine"
        PER_DAY = "per_day", "Per day"
        FLAT = "flat", "Flat"

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.OTHER)
    late_fine_mode = models.CharField(max_length=8, choices=LateFine.choices, default=LateFine.NONE)
    late_fine_amount = models.DecimalField(**MONEY, default=ZERO)
    grace_days = models.PositiveSmallIntegerField(default=0)
    tally_ledger = models.CharField(max_length=100, blank=True, help_text="Income ledger in Tally (defaults to the name)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="fees_head_code_unique")]

    def __str__(self) -> str:
        return self.name


class FeePlan(TimeStamped, BranchOwned):
    """What a class/course pays for one head in one academic year, split into
    instalments. Applied to every active enrolment of that program (and term,
    if set) — automatically when a student is enrolled."""

    name = models.CharField(max_length=150)
    academic_year = models.ForeignKey("people.AcademicYear", on_delete=models.PROTECT, related_name="fee_plans")
    program = models.ForeignKey("people.Program", on_delete=models.PROTECT, related_name="fee_plans")
    term = models.ForeignKey("people.Term", null=True, blank=True, on_delete=models.PROTECT, related_name="fee_plans")
    head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="plans")

    class Meta:
        ordering = ("program__sequence", "head__name")

    def __str__(self) -> str:
        return self.name

    @property
    def total(self) -> Decimal:
        return sum((i.amount for i in self.instalments.all()), ZERO)


class FeePlanInstalment(TimeStamped):
    plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name="instalments")
    sequence = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=60, help_text='e.g. "Q1 (Apr–Jun)"')
    due_date = models.DateField()
    amount = models.DecimalField(**MONEY)

    class Meta:
        ordering = ("plan", "sequence")
        constraints = [
            models.UniqueConstraint(fields=["plan", "sequence"], name="fees_instalment_sequence_unique"),
            models.CheckConstraint(check=Q(amount__gt=0), name="fees_instalment_amount_positive"),
        ]


class Charge(TimeStamped, BranchOwned):
    class Source(models.TextChoices):
        PLAN = "plan", "Fee plan"
        HOSTEL = "hostel", "Hostel"
        MESS = "mess", "Mess"
        GUEST_MEAL = "guest_meal", "Guest meal"
        TRANSPORT = "transport", "Transport"
        LIBRARY = "library", "Library"
        LATE_FINE = "late_fine", "Late fine"
        MANUAL = "manual", "Manual adjustment"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="charges")
    head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="charges")
    academic_year = models.ForeignKey(
        "people.AcademicYear", null=True, blank=True, on_delete=models.PROTECT, related_name="charges"
    )
    description = models.CharField(max_length=200)
    due_date = models.DateField(db_index=True)
    # Negative amounts are allowed only for manual adjustments (credit notes).
    amount = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY, default=ZERO, help_text="From approved concessions")
    source_type = models.CharField(max_length=12, choices=Source.choices)
    source_id = models.CharField(max_length=64, blank=True, help_text="Idempotency key within the source")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="late_fines",
        help_text="For a late fine: the instalment it penalises",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("due_date", "id")
        indexes = [
            models.Index(fields=["student", "due_date"], name="fees_charge_student_due"),
            models.Index(fields=["source_type", "source_id"], name="fees_charge_source"),
        ]
        constraints = [
            # Posting the same thing twice (re-running a plan, a retried hostel
            # month) must not double-bill: one live charge per source key.
            models.UniqueConstraint(
                fields=["student", "source_type", "source_id"],
                condition=Q(cancelled_at__isnull=True) & ~Q(source_id=""),
                name="fees_one_live_charge_per_source",
            ),
            models.CheckConstraint(check=Q(discount__gte=0), name="fees_discount_nonneg"),
            models.CheckConstraint(
                check=Q(amount__gte=0) | Q(source_type="manual"), name="fees_negative_only_manual"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.description} ({self.amount})"

    @property
    def net(self) -> Decimal:
        return self.amount - self.discount


class Concession(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentage"
        FIXED = "fixed", "Fixed amount per instalment"

    class Reason(models.TextChoices):
        SIBLING = "sibling", "Sibling"
        STAFF_WARD = "staff_ward", "Staff ward"
        MERIT = "merit", "Merit"
        RTE = "rte", "RTE"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="concessions")
    head = models.ForeignKey(FeeHead, on_delete=models.PROTECT, related_name="concessions")
    academic_year = models.ForeignKey("people.AcademicYear", on_delete=models.PROTECT, related_name="concessions")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(**MONEY)
    reason = models.CharField(max_length=12, choices=Reason.choices)
    note = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    requested_by = models.CharField(max_length=255, blank=True)
    decided_by = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(check=Q(value__gt=0), name="fees_concession_value_positive"),
            models.CheckConstraint(check=~Q(kind="percent") | Q(value__lte=100), name="fees_concession_percent_max"),
        ]


class ReceiptCounter(BranchOwned):
    """Gap-free numbering: one row per branch and financial year, locked with
    SELECT … FOR UPDATE while a receipt is numbered."""

    financial_year = models.CharField(max_length=7)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "financial_year"], name="fees_counter_unique")
        ]


class Receipt(TimeStamped, BranchOwned):
    class Mode(models.TextChoices):
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"
        DD = "dd", "Demand draft"
        UPI = "upi", "UPI"
        BANK = "bank_transfer", "Bank transfer"

    number = models.CharField(max_length=40)
    financial_year = models.CharField(max_length=7)
    sequence = models.PositiveIntegerField()
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="receipts")
    date = models.DateField(db_index=True)
    mode = models.CharField(max_length=14, choices=Mode.choices)
    reference = models.CharField(max_length=100, blank=True, help_text="Cheque/DD/UTR/UPI reference")
    amount = models.DecimalField(**MONEY)
    received_by = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=200, blank=True)
    print_count = models.PositiveSmallIntegerField(default=0)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=255, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-date", "-sequence")
        constraints = [
            models.UniqueConstraint(fields=["branch", "financial_year", "sequence"], name="fees_receipt_sequence_unique"),
            models.CheckConstraint(check=Q(amount__gt=0), name="fees_receipt_amount_positive"),
        ]

    def __str__(self) -> str:
        return self.number


class ReceiptLine(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="lines")
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, related_name="receipt_lines")
    amount = models.DecimalField(**MONEY)

    class Meta:
        constraints = [models.CheckConstraint(check=Q(amount__gt=0), name="fees_receipt_line_positive")]


class Refund(TimeStamped, BranchOwned):
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="refunds")
    date = models.DateField()
    mode = models.CharField(max_length=14, choices=Receipt.Mode.choices)
    reference = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(**MONEY)
    reason = models.CharField(max_length=200)
    created_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-date", "-id")
        constraints = [models.CheckConstraint(check=Q(amount__gt=0), name="fees_refund_amount_positive")]


class RefundLine(models.Model):
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="lines")
    charge = models.ForeignKey(Charge, on_delete=models.PROTECT, related_name="refund_lines")
    amount = models.DecimalField(**MONEY)

    class Meta:
        constraints = [models.CheckConstraint(check=Q(amount__gt=0), name="fees_refund_line_positive")]


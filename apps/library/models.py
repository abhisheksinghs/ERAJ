"""
Library module models. This app is in TENANT_APPS: a fresh copy of these
tables is created in EVERY tenant schema. There is deliberately NO
tenant_id/client foreign key — isolation comes from the Postgres schema
itself (see docs/FAILURE_MODES.md).
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.mixins import SoftDelete, TimeStamped


class Category(TimeStamped):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Book(TimeStamped, SoftDelete):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    isbn = models.CharField(max_length=20, unique=True)
    publisher = models.CharField(max_length=255, blank=True)
    published_year = models.PositiveSmallIntegerField(null=True, blank=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="books"
    )
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    shelf_location = models.CharField(max_length=50, blank=True)
    copies_total = models.PositiveIntegerField(default=1)
    copies_available = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("title",)
        constraints = [
            models.CheckConstraint(
                check=Q(copies_available__gte=0), name="library_book_available_nonneg"
            ),
            models.CheckConstraint(
                check=Q(copies_available__lte=F("copies_total")),
                name="library_book_available_lte_total",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Member(TimeStamped, SoftDelete):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    # Per-member override; None -> settings.LIBRARY_DEFAULT_BORROW_LIMIT.
    max_books = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("full_name",)

    def __str__(self) -> str:
        return self.full_name

    @property
    def effective_borrow_limit(self) -> int:
        return self.max_books or settings.LIBRARY_DEFAULT_BORROW_LIMIT

    @property
    def open_loan_count(self) -> int:
        return self.issues.filter(returned_at__isnull=True).count()


class Issue(TimeStamped):
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="issues")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="issues")
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    renewals = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["book", "member"],
                condition=Q(returned_at__isnull=True),
                name="library_one_open_loan_per_book_member",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.book} -> {self.member}"

    @property
    def is_returned(self) -> bool:
        return self.returned_at is not None

    @property
    def is_overdue(self) -> bool:
        return not self.is_returned and self.due_date < timezone.localdate()


class Fine(TimeStamped):
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="fines")
    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="fines")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    reason = models.CharField(max_length=255, default="overdue return")
    paid = models.BooleanField(default=False)
    waived = models.BooleanField(default=False)
    waived_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.member} — {self.amount}"

    @property
    def outstanding(self) -> Decimal:
        return Decimal("0.00") if (self.paid or self.waived) else self.amount


class Hold(TimeStamped):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        READY = "ready", "Ready for pickup"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="holds")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="holds")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["book", "member"],
                condition=Q(status__in=["waiting", "ready"]),
                name="library_one_active_hold_per_book_member",
            ),
        ]

    def __str__(self) -> str:
        return f"hold: {self.book} for {self.member} ({self.status})"

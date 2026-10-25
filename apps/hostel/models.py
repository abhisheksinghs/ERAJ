"""
Hostel module models. In TENANT_APPS — one copy per tenant schema, no
tenant FK (isolation is the schema).

Residence is modelled as an `Allocation` (student <-> room, with dates) so
vacating keeps history and capacity is enforced against the count of *active*
allocations. Residents are `people.Student` rows (ADR-002); every row here is
branch-owned (ADR-001).
"""
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.mixins import SoftDelete, TimeStamped
from apps.org.models import BranchOwned


class Room(TimeStamped, SoftDelete, BranchOwned):
    class Type(models.TextChoices):
        SINGLE = "single", "Single"
        DOUBLE = "double", "Double"
        DORM = "dorm", "Dormitory"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        ANY = "any", "Any"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "Under maintenance"
        DECOMMISSIONED = "decommissioned", "Decommissioned"

    number = models.CharField(max_length=20)
    capacity = models.PositiveSmallIntegerField(default=2)
    room_type = models.CharField(max_length=10, choices=Type.choices, default=Type.DOUBLE)
    gender = models.CharField(max_length=6, choices=Gender.choices, default=Gender.ANY)
    floor = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ("number",)
        constraints = [models.UniqueConstraint(fields=["branch", "number"], name="hostel_room_number_unique")]

    def __str__(self) -> str:
        return self.number

    @property
    def occupied(self) -> int:
        return self.allocations.filter(check_out_date__isnull=True).count()

    @property
    def available_beds(self) -> int:
        return max(0, self.capacity - self.occupied)

    @property
    def has_open_maintenance(self) -> bool:
        return self.maintenance_tickets.filter(status=MaintenanceTicket.Status.OPEN).exists()


class Allocation(TimeStamped, BranchOwned):
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="hostel_allocations")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="allocations")
    check_in_date = models.DateField(default=timezone.localdate)
    check_out_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-check_in_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(check_out_date__isnull=True),
                name="hostel_one_active_allocation_per_student",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} @ {self.room}"

    @property
    def is_active(self) -> bool:
        return self.check_out_date is None


class Waitlist(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        OFFERED = "offered", "Offered"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="hostel_waitlist_entries")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="waitlist")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["student", "room"],
                condition=Q(status__in=["waiting", "offered"]),
                name="hostel_one_active_waitlist_entry_per_student_room",
            ),
        ]

    def __str__(self) -> str:
        return f"waitlist: {self.student} -> {self.room} ({self.status})"


class MaintenanceTicket(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="maintenance_tickets")
    summary = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.room}: {self.summary} ({self.status})"

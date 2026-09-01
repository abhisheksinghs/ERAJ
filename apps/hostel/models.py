"""
Hostel module models. In TENANT_APPS — one copy per tenant schema, no
tenant FK (isolation is the schema).

Residence is modelled as an `Allocation` (resident <-> room, with dates) rather
than a plain FK on Resident, so vacating keeps history and capacity can be
enforced against the count of *active* allocations.
"""
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.mixins import SoftDelete, TimeStamped


class Room(TimeStamped, SoftDelete):
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

    number = models.CharField(max_length=20, unique=True)
    capacity = models.PositiveSmallIntegerField(default=2)
    room_type = models.CharField(max_length=10, choices=Type.choices, default=Type.DOUBLE)
    gender = models.CharField(max_length=6, choices=Gender.choices, default=Gender.ANY)
    floor = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ("number",)

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


class Resident(TimeStamped, SoftDelete):
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    guardian_name = models.CharField(max_length=255, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ("full_name",)

    def __str__(self) -> str:
        return self.full_name

    @property
    def current_allocation(self):
        return (
            self.allocations.filter(check_out_date__isnull=True)
            .select_related("room")
            .first()
        )


class Allocation(TimeStamped):
    resident = models.ForeignKey(Resident, on_delete=models.PROTECT, related_name="allocations")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="allocations")
    check_in_date = models.DateField(default=timezone.localdate)
    check_out_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-check_in_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["resident"],
                condition=Q(check_out_date__isnull=True),
                name="hostel_one_active_allocation_per_resident",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.resident} @ {self.room}"

    @property
    def is_active(self) -> bool:
        return self.check_out_date is None


class Waitlist(TimeStamped):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        OFFERED = "offered", "Offered"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    resident = models.ForeignKey(Resident, on_delete=models.CASCADE, related_name="waitlist_entries")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="waitlist")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["resident", "room"],
                condition=Q(status__in=["waiting", "offered"]),
                name="hostel_one_active_waitlist_entry_per_resident_room",
            ),
        ]

    def __str__(self) -> str:
        return f"waitlist: {self.resident} -> {self.room} ({self.status})"


class MaintenanceTicket(TimeStamped):
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

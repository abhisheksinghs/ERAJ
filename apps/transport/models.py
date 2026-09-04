"""Transport module. TENANT_APPS. A rider is captured as freetext fields on
the assignment rather than a full person model — no other module needs to
reference "who rides the bus", so a registry would be speculative (YAGNI)."""
from django.db import models

from apps.core.mixins import SoftDelete, TimeStamped


class Route(TimeStamped):
    name = models.CharField(max_length=100, unique=True)
    stops = models.TextField(blank=True, help_text="One stop per line")

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Vehicle(TimeStamped, SoftDelete):
    number = models.CharField(max_length=20, unique=True)
    capacity = models.PositiveSmallIntegerField(default=40)
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL, related_name="vehicles")

    class Meta:
        ordering = ("number",)

    def __str__(self) -> str:
        return self.number

    @property
    def active_riders(self) -> int:
        return self.assignments.filter(removed_at__isnull=True).count()

    @property
    def available_seats(self) -> int:
        return max(0, self.capacity - self.active_riders)


class TransportAssignment(TimeStamped):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="assignments")
    rider_name = models.CharField(max_length=255)
    rider_contact = models.CharField(max_length=20, blank=True)
    pickup_point = models.CharField(max_length=255, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.rider_name} -> {self.vehicle}"

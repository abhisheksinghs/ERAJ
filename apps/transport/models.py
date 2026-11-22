"""
Transport (ADR-010). Branch-owned (ADR-001); riders are students or staff from
the shared registry (ADR-002); student fares post to the Fees ledger (ADR-003);
GPS arrives through a push endpoint or the staging simulator (ADR-005).
"""
from __future__ import annotations

import secrets

from django.db import models
from django.db.models import Q

from apps.core.mixins import SoftDelete, TimeStamped
from apps.org.models import BranchOwned

MONEY = {"max_digits": 12, "decimal_places": 2}


def _key() -> str:
    return secrets.token_urlsafe(32)


class TransportSettings(TimeStamped, BranchOwned):
    speed_limit_kmph = models.PositiveSmallIntegerField(default=40)
    near_stop_meters = models.PositiveIntegerField(default=500, help_text='"Bus near your stop" alert distance')
    document_remind_days = models.PositiveSmallIntegerField(default=30)

    class Meta:
        verbose_name_plural = "transport settings"
        constraints = [models.UniqueConstraint(fields=["branch"], name="transport_one_settings_per_branch")]


class FareSlab(TimeStamped, BranchOwned):
    from_km = models.DecimalField(max_digits=6, decimal_places=2)
    to_km = models.DecimalField(max_digits=6, decimal_places=2)
    monthly_fare = models.DecimalField(**MONEY)

    class Meta:
        ordering = ("from_km",)
        constraints = [models.CheckConstraint(check=Q(to_km__gt=models.F("from_km")), name="transport_slab_range")]

    def __str__(self) -> str:
        return f"{self.from_km}–{self.to_km} km: ₹{self.monthly_fare}"


class Route(TimeStamped, SoftDelete, BranchOwned):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("code",)
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="transport_route_code_unique")]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class RouteStop(TimeStamped, BranchOwned):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    sequence = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=120)
    name_hi = models.CharField(max_length=120, blank=True)
    pickup_time = models.TimeField(null=True, blank=True)
    drop_time = models.TimeField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="From the campus")
    monthly_fare = models.DecimalField(**MONEY, null=True, blank=True, help_text="Empty = from the distance slab")

    class Meta:
        ordering = ("route", "sequence")
        constraints = [models.UniqueConstraint(fields=["route", "sequence"], name="transport_stop_sequence_unique")]

    def __str__(self) -> str:
        return f"{self.sequence}. {self.name}"


class Vehicle(TimeStamped, SoftDelete, BranchOwned):
    class Kind(models.TextChoices):
        BUS = "bus", "Bus"
        MINIBUS = "minibus", "Mini-bus"
        VAN = "van", "Van"
        AUTO = "auto", "Auto / e-rickshaw"
        OTHER = "other", "Other"

    registration_no = models.CharField(max_length=20)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.BUS)
    capacity = models.PositiveSmallIntegerField(default=40)
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL, related_name="vehicles")
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    helper_name = models.CharField(max_length=100, blank=True)
    helper_phone = models.CharField(max_length=20, blank=True)
    gps_device_id = models.CharField(max_length=60, blank=True, help_text="Tracker IMEI / provider's vehicle id")
    gps_key = models.CharField(max_length=64, default=_key, unique=True, editable=False)
    gps_allowed_ips = models.CharField(max_length=255, blank=True, help_text="Comma separated; blank = any")
    is_active = models.BooleanField(default=True)
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_speed_kmph = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("registration_no",)
        constraints = [models.UniqueConstraint(fields=["branch", "registration_no"], name="transport_vehicle_reg_unique")]

    def __str__(self) -> str:
        return self.registration_no

    def ip_allowed(self, ip: str | None) -> bool:
        allowed = {x.strip() for x in self.gps_allowed_ips.split(",") if x.strip()}
        return not allowed or (ip in allowed)


class VehicleDocument(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        INSURANCE = "insurance", "Insurance"
        FITNESS = "fitness", "Fitness certificate"
        PERMIT = "permit", "Permit"
        POLLUTION = "pollution", "Pollution certificate"
        OTHER = "other", "Other"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    number = models.CharField(max_length=60, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("expires_on",)


class TransportAssignment(TimeStamped, BranchOwned):
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.PROTECT, related_name="transport")
    staff = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="transport")
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="assignments")
    stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="assignments")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="assignments")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Last day riding; empty = still riding")
    monthly_fare = models.DecimalField(**MONEY, default=0)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("route", "stop__sequence")
        constraints = [
            models.CheckConstraint(
                check=(Q(student__isnull=False) & Q(staff__isnull=True)) | (Q(student__isnull=True) & Q(staff__isnull=False)),
                name="transport_rider_student_xor_staff"),
            models.CheckConstraint(check=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                                   name="transport_assignment_dates"),
        ]
        indexes = [models.Index(fields=["vehicle", "end_date"], name="transport_asg_vehicle_end")]

    @property
    def rider(self):
        return self.student or self.staff


class VehiclePosition(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="positions")
    recorded_at = models.DateTimeField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    speed_kmph = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("vehicle", "recorded_at")
        constraints = [models.UniqueConstraint(fields=["vehicle", "recorded_at"], name="transport_position_unique")]


class TransportAlert(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        NEAR_STOP = "near_stop", "Bus near the stop"
        OVER_SPEED = "over_speed", "Over-speed"
        DOCUMENT = "document", "Document expiring"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    stop = models.ForeignKey(RouteStop, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts")
    at = models.DateTimeField()
    key = models.CharField(max_length=80, help_text="De-duplication key (vehicle/stop/day/session)")
    detail = models.CharField(max_length=255, blank=True)
    recipients = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-at",)
        constraints = [models.UniqueConstraint(fields=["branch", "key"], name="transport_alert_once")]

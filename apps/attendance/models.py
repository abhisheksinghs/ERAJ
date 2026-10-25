"""
Attendance (ADR-008). TENANT app; rows are branch-owned (ADR-001) and point at
the shared `people.Student` / `people.Staff` (ADR-002).

`period` is NULL for once-a-day marking (schools) and holds the lecture number
for per-lecture marking (colleges/coaching); `subject` is set with it.
"""
import secrets

from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class AttendanceSettings(TimeStamped, BranchOwned):
    class Mode(models.TextChoices):
        DAILY = "daily", "Once a day"
        PER_LECTURE = "per_lecture", "Per lecture / subject"

    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.DAILY)
    weekly_off = models.CharField(max_length=20, default="6", help_text="Weekdays off, 0=Mon … 6=Sun, comma separated")
    threshold_percent = models.PositiveSmallIntegerField(default=75)
    long_absence_days = models.PositiveSmallIntegerField(default=5)
    auto_mark_from_punches = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "attendance settings"
        constraints = [models.UniqueConstraint(fields=["branch"], name="attendance_one_settings_per_branch")]

    @property
    def weekly_off_days(self) -> set[int]:
        return {int(x) for x in self.weekly_off.split(",") if x.strip().isdigit()}


class Holiday(TimeStamped, BranchOwned):
    date = models.DateField()
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("date",)
        constraints = [models.UniqueConstraint(fields=["branch", "date"], name="attendance_holiday_unique")]

    def __str__(self) -> str:
        return f"{self.date}: {self.name}"


class AttendanceRecord(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LEAVE = "leave", "Leave"
        LATE = "late", "Late"
        HALF_DAY = "half_day", "Half-day"

    class Source(models.TextChoices):
        MANUAL = "manual", "Marked by teacher"
        DEVICE = "device", "Attendance device"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="attendance_records")
    section = models.ForeignKey("people.Section", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateField(db_index=True)
    period = models.PositiveSmallIntegerField(null=True, blank=True)
    subject = models.ForeignKey("people.Subject", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    source = models.CharField(max_length=6, choices=Source.choices, default=Source.MANUAL)
    marked_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-date", "period")
        indexes = [models.Index(fields=["section", "date"], name="attendance_section_date_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "date", "period"],
                nulls_distinct=False,
                name="attendance_one_record_per_student_day_period",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.date} ({self.status})"


# ------------------------------------------------------------------ devices
def _token() -> str:
    return secrets.token_urlsafe(24)


class AttendanceDevice(TimeStamped, BranchOwned):
    class Brand(models.TextChoices):
        ZKTECO = "zkteco", "ZKTeco (ADMS push)"
        ESSL = "essl", "eSSL (ADMS push)"
        REALTIME = "realtime", "Realtime (ADMS push)"
        IDENTIX = "identix", "Identix (ADMS push)"
        GENERIC = "generic", "Other — JSON push"
        FILE = "file", "Other — Excel/CSV import only"

    ADMS_BRANDS = {Brand.ZKTECO, Brand.ESSL, Brand.REALTIME, Brand.IDENTIX}

    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=10, choices=Brand.choices)
    model = models.CharField(max_length=60, blank=True)
    serial_no = models.CharField(max_length=60, unique=True, help_text="As shown on the device; ADMS devices send it")
    location = models.CharField(max_length=100, blank=True)
    token = models.CharField(max_length=64, default=_token, unique=True, editable=False)
    allowed_ips = models.CharField(max_length=255, blank=True, help_text="Comma separated; blank = any")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.serial_no})"

    def ip_allowed(self, ip: str | None) -> bool:
        allowed = {x.strip() for x in self.allowed_ips.split(",") if x.strip()}
        return not allowed or (ip in allowed)


class AttendanceCard(TimeStamped, BranchOwned):
    """Card number / device user id → student or staff member."""

    code = models.CharField(max_length=40)
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.CASCADE, related_name="attendance_cards")
    staff = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.CASCADE, related_name="attendance_cards")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="attendance_card_code_unique"),
            models.CheckConstraint(
                check=(Q(student__isnull=False) & Q(staff__isnull=True)) | (Q(student__isnull=True) & Q(staff__isnull=False)),
                name="attendance_card_student_xor_staff",
            ),
        ]


class Punch(TimeStamped, BranchOwned):
    class Source(models.TextChoices):
        PUSH = "push", "Device push"
        IMPORT = "import", "File import"

    device = models.ForeignKey(AttendanceDevice, null=True, blank=True, on_delete=models.SET_NULL, related_name="punches")
    code = models.CharField(max_length=40)
    punched_at = models.DateTimeField(db_index=True)
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.SET_NULL, related_name="punches")
    staff = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="punches")
    source = models.CharField(max_length=6, choices=Source.choices)

    class Meta:
        ordering = ("-punched_at",)
        constraints = [models.UniqueConstraint(fields=["branch", "code", "punched_at"], name="attendance_punch_unique")]

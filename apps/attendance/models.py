"""
Attendance module. TENANT app; rows are branch-owned (ADR-001) and point at the
shared `people.Student` (ADR-002).

`period` is NULL for once-a-day marking (schools) and holds the lecture number
for per-lecture marking (colleges/coaching); `subject` is set with it.
"""
from django.db import models

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class AttendanceRecord(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LEAVE = "leave", "Leave"
        LATE = "late", "Late"
        HALF_DAY = "half_day", "Half-day"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="attendance_records")
    date = models.DateField(db_index=True)
    period = models.PositiveSmallIntegerField(null=True, blank=True)
    subject = models.ForeignKey("people.Subject", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    marked_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-date", "period")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "date", "period"],
                nulls_distinct=False,
                name="attendance_one_record_per_student_day_period",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.date} ({self.status})"

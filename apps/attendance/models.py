"""
Attendance module. TENANT_APPS — one copy per tenant schema.

`Student` is kept local to this app rather than shared with other modules
that also need a "person" concept (Fees, Exam) — see
docs/REQUIREMENTS_GAP_ANALYSIS.md's modeling note: independent per-module
records over one cross-module registry, matching the Library/Hostel pattern
already built (Member, Resident are likewise module-local).
"""
from django.db import models

from apps.core.mixins import SoftDelete, TimeStamped


class Student(TimeStamped, SoftDelete):
    full_name = models.CharField(max_length=255)
    roll_no = models.CharField(max_length=50, unique=True)
    class_section = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ("full_name",)

    def __str__(self) -> str:
        return f"{self.full_name} ({self.roll_no})"


class AttendanceRecord(TimeStamped):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LEAVE = "leave", "Leave"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    marked_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(fields=["student", "date"], name="attendance_one_record_per_student_per_day"),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.date} ({self.status})"

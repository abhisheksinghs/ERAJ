"""
Exam module. TENANT_APPS.

`Student` is module-local, same as Attendance's — see
docs/REQUIREMENTS_GAP_ANALYSIS.md's modeling note (independent per-module
records, not a shared cross-module registry). Duplicated with
Attendance.Student for now; unify behind one `apps.people` app if double
data-entry becomes a real complaint.
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


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ExamResult(TimeStamped):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="results")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="results")
    exam_name = models.CharField(max_length=100, help_text='e.g. "Midterm 2026"')
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "exam_name"], name="exam_one_result_per_student_subject_exam"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.subject} ({self.exam_name})"

    @property
    def percentage(self) -> float:
        return round(float(self.marks_obtained) / float(self.max_marks) * 100, 1) if self.max_marks else 0.0

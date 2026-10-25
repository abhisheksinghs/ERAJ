"""
Exam module. TENANT app; branch-owned rows (ADR-001) on the shared
`people.Student` / `people.Subject` (ADR-002). M3 adds exams, grade scales,
locking, SGPA/CGPA and report cards on top of this.
"""
from django.db import models

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class ExamResult(TimeStamped, BranchOwned):
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="exam_results")
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="exam_results")
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

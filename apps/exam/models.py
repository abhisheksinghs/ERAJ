"""
Exam (ADR-008). TENANT app; branch-owned rows (ADR-001) on the shared
`people.Student` / `people.Subject` / `people.Section` (ADR-002).

Results (totals, %, grade, rank, SGPA/CGPA) are computed from `Mark` rows,
never stored, so a correction always shows everywhere.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned

MARKS = {"max_digits": 6, "decimal_places": 2}


class GradeScale(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        MARKS = "marks", "Marks → grade (school)"
        CREDIT = "credit", "Credit-based SGPA/CGPA (college)"

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.MARKS)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def band_for(self, percent: Decimal):
        for band in self.bands.all():  # ordered by min_percent desc
            if percent >= band.min_percent:
                return band
        return None


class GradeBand(TimeStamped):
    scale = models.ForeignKey(GradeScale, on_delete=models.CASCADE, related_name="bands")
    grade = models.CharField(max_length=5)
    min_percent = models.DecimalField(max_digits=5, decimal_places=2)
    grade_point = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0"))
    is_fail = models.BooleanField(default=False)
    remark = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ("scale", "-min_percent")
        constraints = [models.UniqueConstraint(fields=["scale", "grade"], name="exam_band_grade_unique")]


class Exam(TimeStamped, BranchOwned):
    name = models.CharField(max_length=100, help_text='e.g. "Half-Yearly"')
    name_hi = models.CharField(max_length=100, blank=True)
    academic_year = models.ForeignKey("people.AcademicYear", on_delete=models.PROTECT, related_name="exams")
    program = models.ForeignKey("people.Program", on_delete=models.PROTECT, related_name="exams")
    term = models.ForeignKey("people.Term", null=True, blank=True, on_delete=models.PROTECT, related_name="exams")
    scale = models.ForeignKey(GradeScale, on_delete=models.PROTECT, related_name="exams")
    weightage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"),
                                    help_text="% of the final (annual) result; 0 = not counted")
    is_term_final = models.BooleanField(default=False, help_text="Counts for SGPA/CGPA (credit scales)")
    sequence = models.PositiveSmallIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("academic_year", "program", "sequence")
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "program", "term", "name"], nulls_distinct=False,
                                    name="exam_unique_name_per_class_year"),
        ]

    def __str__(self) -> str:
        return f"{self.name} — {self.program}"


class ExamSubject(TimeStamped, BranchOwned):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="subjects")
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="exam_subjects")
    max_theory = models.DecimalField(**MARKS, default=Decimal("100"))
    max_practical = models.DecimalField(**MARKS, default=Decimal("0"))
    pass_marks = models.DecimalField(**MARKS, default=Decimal("33"))
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=180)
    sequence = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("exam", "sequence", "subject__name")
        constraints = [
            models.UniqueConstraint(fields=["exam", "subject"], name="exam_subject_once_per_exam"),
            models.CheckConstraint(check=Q(max_theory__gte=0) & Q(max_practical__gte=0), name="exam_subject_max_nonneg"),
        ]

    @property
    def max_total(self) -> Decimal:
        return self.max_theory + self.max_practical


class Mark(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent (AB)"
        EXEMPT = "exempt", "Exempt"

    exam_subject = models.ForeignKey(ExamSubject, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="marks")
    theory = models.DecimalField(**MARKS, null=True, blank=True)
    practical = models.DecimalField(**MARKS, null=True, blank=True)
    status = models.CharField(max_length=7, choices=Status.choices, default=Status.PRESENT)
    entered_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("exam_subject", "student")
        constraints = [models.UniqueConstraint(fields=["exam_subject", "student"], name="exam_one_mark_per_student_subject")]


class ExamLock(TimeStamped, BranchOwned):
    """Marks of `exam` for `section` are locked (class teacher), until Admin unlocks."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="locks")
    section = models.ForeignKey("people.Section", on_delete=models.CASCADE, related_name="exam_locks")
    locked_by = models.CharField(max_length=255)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "section"], name="exam_lock_once")]

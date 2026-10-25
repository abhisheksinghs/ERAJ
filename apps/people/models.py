"""
The shared registry (ADR-002): every module points at these records instead of
keeping its own copy of a person.

Academic structure is configurable per institution type:
  school   → Program(kind=school_class) "Class 6", one Term, Sections A/B
  college  → Program(kind=course) "B.Com", Terms "Semester 1..6", Sections
  coaching → Program(kind=batch) "JEE 2027", optional Terms, Sections = batches
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.mixins import SoftDelete, TimeStamped
from apps.org.models import BranchOwned


class AcademicYear(TimeStamped):
    """Client-wide (not per branch): branches of one trust share the session."""

    name = models.CharField(max_length=20, unique=True, help_text='e.g. "2026-27"')
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ("-start_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"], condition=Q(is_current=True), name="people_one_current_year"
            ),
            models.CheckConstraint(check=Q(end_date__gt=models.F("start_date")), name="people_year_dates"),
        ]

    def __str__(self) -> str:
        return self.name


class Department(TimeStamped, BranchOwned):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="people_department_unique")]

    def __str__(self) -> str:
        return self.name


class Program(TimeStamped, SoftDelete, BranchOwned):
    class Kind(models.TextChoices):
        SCHOOL_CLASS = "school_class", "Class"
        COURSE = "course", "Course"
        BATCH = "batch", "Batch"

    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)
    code = models.CharField(max_length=20)
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.SCHOOL_CLASS)
    sequence = models.PositiveSmallIntegerField(default=0, help_text="Order for promotion and lists")

    class Meta:
        ordering = ("sequence", "name")
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="people_program_code_unique")]

    def __str__(self) -> str:
        return self.name


class Term(TimeStamped, BranchOwned):
    """A semester or term of a program. Schools typically have one ("Annual")."""

    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=50)
    sequence = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("program", "sequence")
        constraints = [models.UniqueConstraint(fields=["program", "sequence"], name="people_term_unique")]

    def __str__(self) -> str:
        return f"{self.program} — {self.name}"


class Subject(TimeStamped, SoftDelete, BranchOwned):
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)
    code = models.CharField(max_length=20)
    program = models.ForeignKey(Program, null=True, blank=True, on_delete=models.SET_NULL, related_name="subjects")
    term = models.ForeignKey(Term, null=True, blank=True, on_delete=models.SET_NULL, related_name="subjects")
    credits = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    has_practical = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="people_subject_code_unique")]

    def __str__(self) -> str:
        return self.name


class Staff(TimeStamped, SoftDelete, BranchOwned):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LEFT = "left", "Left"

    class EmploymentType(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        CONTRACT = "contract", "Contract"
        PART_TIME = "part_time", "Part-time"

    employee_code = models.CharField(max_length=30)
    full_name = models.CharField(max_length=255)
    name_hi = models.CharField(max_length=255, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(default=timezone.localdate)
    employment_type = models.CharField(max_length=10, choices=EmploymentType.choices, default=EmploymentType.PERMANENT)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff_profile"
    )

    class Meta:
        ordering = ("full_name",)
        verbose_name_plural = "staff"
        constraints = [models.UniqueConstraint(fields=["branch", "employee_code"], name="people_staff_code_unique")]

    def __str__(self) -> str:
        return self.full_name


class Student(TimeStamped, SoftDelete, BranchOwned):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PASSED_OUT = "passed_out", "Passed out"
        LEFT = "left", "Left"

    admission_no = models.CharField(max_length=30)
    full_name = models.CharField(max_length=255)
    name_hi = models.CharField("name (Hindi)", max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=6, choices=Gender.choices, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    photo = models.ImageField(upload_to="students/%Y/", null=True, blank=True)
    admission_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="student_profile"
    )

    class Meta:
        ordering = ("full_name",)
        constraints = [models.UniqueConstraint(fields=["branch", "admission_no"], name="people_admission_no_unique")]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.admission_no})"

    @property
    def current_enrollment(self):
        return (
            self.enrollments.filter(academic_year__is_current=True, status=Enrollment.Status.ACTIVE)
            .select_related("program", "term", "section")
            .order_by("-term__sequence")
            .first()
        )


class Guardian(TimeStamped, BranchOwned):
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, db_index=True)
    alt_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="guardian_profile"
    )
    students = models.ManyToManyField(Student, through="StudentGuardian", related_name="guardians")

    class Meta:
        ordering = ("full_name",)

    def __str__(self) -> str:
        return f"{self.full_name} ({self.phone})"


class StudentGuardian(TimeStamped, BranchOwned):
    class Relation(models.TextChoices):
        FATHER = "father", "Father"
        MOTHER = "mother", "Mother"
        GUARDIAN = "guardian", "Guardian"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(Guardian, on_delete=models.CASCADE, related_name="student_links")
    relation = models.CharField(max_length=10, choices=Relation.choices, default=Relation.GUARDIAN)
    is_primary = models.BooleanField(default=False, help_text="Receives alerts and the portal login")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "guardian"], name="people_student_guardian_unique"),
            models.UniqueConstraint(
                fields=["student"], condition=Q(is_primary=True), name="people_one_primary_guardian"
            ),
        ]


class Section(TimeStamped, BranchOwned):
    """A section of a program in a year (school "6-A", college division, coaching batch)."""

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="sections")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="sections")
    term = models.ForeignKey(Term, null=True, blank=True, on_delete=models.PROTECT, related_name="sections")
    name = models.CharField(max_length=30)
    class_teacher = models.ForeignKey(
        Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name="class_sections"
    )
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("program__sequence", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "program", "term", "name"],
                nulls_distinct=False,
                name="people_section_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.program}-{self.name}"


class Enrollment(TimeStamped, BranchOwned):
    """Which program/term/section a student is in for a year — the single
    source Attendance, Exam, Fees and Timetable read."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PROMOTED = "promoted", "Promoted"
        LEFT = "left", "Left"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="enrollments")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="enrollments")
    term = models.ForeignKey(Term, null=True, blank=True, on_delete=models.PROTECT, related_name="enrollments")
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrollments")
    roll_no = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ("section", "roll_no")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year", "term"],
                nulls_distinct=False,
                name="people_one_enrollment_per_term",
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.program} {self.academic_year}"

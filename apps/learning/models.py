"""
Homework and online learning (ADR-011). Branch-owned (ADR-001); teachers act on their own
teaching assignments (people.TeachingAssignment, ADR-008); files are private (core.files).
"""
from __future__ import annotations

from django.db import models
from django.db.models import Q

from apps.core.files import random_path
from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class _File(models.Model):
    file = models.FileField(upload_to=random_path("learning"))
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True


class Homework(TimeStamped, BranchOwned):
    section = models.ForeignKey("people.Section", on_delete=models.PROTECT, related_name="homework")
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="homework")
    teacher = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="homework_set")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    created_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-due_date", "-pk")
        indexes = [models.Index(fields=["section", "due_date"], name="learning_hw_section_due")]

    def __str__(self) -> str:
        return self.title


class HomeworkFile(_File):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name="files")


class Submission(TimeStamped, BranchOwned):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="submissions")
    text = models.TextField(blank=True)
    submitted_at = models.DateTimeField()
    late = models.BooleanField(default=False)
    grade = models.CharField(max_length=10, blank=True)
    remarks = models.CharField(max_length=500, blank=True)
    reviewed_by = models.CharField(max_length=255, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("homework", "student__full_name")
        constraints = [models.UniqueConstraint(fields=["homework", "student"], name="learning_one_submission")]


class SubmissionFile(_File):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="files")


class Material(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        NOTE = "note", "Notes"
        FILE = "file", "File (PDF / slides)"
        VIDEO = "video", "Video link"
        LINK = "link", "Web link"

    program = models.ForeignKey("people.Program", null=True, blank=True, on_delete=models.CASCADE, related_name="materials")
    section = models.ForeignKey("people.Section", null=True, blank=True, on_delete=models.CASCADE, related_name="materials",
                                help_text="Empty = every section of the class")
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="materials")
    chapter = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=5, choices=Kind.choices, default=Kind.NOTE)
    link = models.URLField(blank=True)
    file = models.FileField(upload_to=random_path("learning"), blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    teacher = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="materials")

    class Meta:
        ordering = ("subject", "chapter", "title")


class OnlineClass(TimeStamped, BranchOwned):
    section = models.ForeignKey("people.Section", on_delete=models.PROTECT, related_name="online_classes")
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="online_classes")
    teacher = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="online_classes")
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    link = models.URLField(help_text="Google Meet / Zoom / similar link")

    class Meta:
        ordering = ("-starts_at",)
        constraints = [models.CheckConstraint(check=Q(ends_at__gt=models.F("starts_at")), name="learning_class_times")]


class JoinRecord(models.Model):
    online_class = models.ForeignKey(OnlineClass, on_delete=models.CASCADE, related_name="joins")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="class_joins")
    first_opened_at = models.DateTimeField()
    opens = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("first_opened_at",)
        constraints = [models.UniqueConstraint(fields=["online_class", "student"], name="learning_join_once")]


class OnlineTest(TimeStamped, BranchOwned):
    section = models.ForeignKey("people.Section", on_delete=models.PROTECT, related_name="online_tests")
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="online_tests")
    teacher = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="online_tests")
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    time_limit_minutes = models.PositiveSmallIntegerField(default=20)
    published = models.BooleanField(default=False, help_text="Students can take it between the open and close times")
    show_answers = models.BooleanField(default=False, help_text="Show correct answers after submitting")

    class Meta:
        ordering = ("-opens_at",)
        constraints = [models.CheckConstraint(check=Q(closes_at__gt=models.F("opens_at")), name="learning_test_window")]


class Question(models.Model):
    test = models.ForeignKey(OnlineTest, on_delete=models.CASCADE, related_name="questions")
    sequence = models.PositiveSmallIntegerField()
    text = models.TextField()
    options = models.JSONField(help_text="2 to 6 choices")
    correct = models.PositiveSmallIntegerField(help_text="Index of the right choice, 0 = first")
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        ordering = ("test", "sequence")
        constraints = [models.UniqueConstraint(fields=["test", "sequence"], name="learning_question_seq")]


class Attempt(TimeStamped, BranchOwned):
    test = models.ForeignKey(OnlineTest, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="test_attempts")
    started_at = models.DateTimeField()
    deadline = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    auto_submitted = models.BooleanField(default=False)

    class Meta:
        ordering = ("test", "student__full_name")
        constraints = [models.UniqueConstraint(fields=["test", "student"], name="learning_one_attempt")]


class DiaryEntry(TimeStamped, BranchOwned):
    section = models.ForeignKey("people.Section", on_delete=models.PROTECT, related_name="diary")
    date = models.DateField()
    period = models.PositiveSmallIntegerField(null=True, blank=True)
    subject = models.ForeignKey("people.Subject", on_delete=models.PROTECT, related_name="diary")
    teacher = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="diary")
    topic = models.CharField(max_length=300)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-date", "period")

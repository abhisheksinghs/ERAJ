"""
Timetable and substitution (ADR-008). TENANT app, branch-owned rows on the
shared Section / Staff / TeachingAssignment (ADR-002).
"""
from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned

DEFAULT_MAX_PERIODS = 36
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class BellSchedule(TimeStamped, BranchOwned):
    """Period timings. Sections not listed on any schedule use the default one."""

    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    sections = models.ManyToManyField("people.Section", blank=True, related_name="bell_schedules")

    class Meta:
        ordering = ("-is_default", "name")
        constraints = [
            models.UniqueConstraint(fields=["branch"], condition=Q(is_default=True), name="timetable_one_default_schedule"),
        ]

    def __str__(self) -> str:
        return self.name


class PeriodSlot(TimeStamped):
    schedule = models.ForeignKey(BellSchedule, on_delete=models.CASCADE, related_name="slots")
    number = models.PositiveSmallIntegerField(help_text="Period number; breaks too, for ordering")
    label = models.CharField(max_length=30, help_text='e.g. "Period 1", "Lunch"')
    start = models.TimeField()
    end = models.TimeField()
    is_break = models.BooleanField(default=False)
    days = models.CharField(max_length=20, default="0,1,2,3,4,5", help_text="Weekdays this slot runs, 0=Mon … 6=Sun")

    class Meta:
        ordering = ("schedule", "number")
        constraints = [
            models.UniqueConstraint(fields=["schedule", "number"], name="timetable_slot_number_unique"),
            models.CheckConstraint(check=Q(end__gt=models.F("start")), name="timetable_slot_times"),
        ]

    def __str__(self) -> str:
        return f"{self.label} {self.start:%H:%M}–{self.end:%H:%M}"

    @property
    def weekdays(self) -> set[int]:
        return {int(x) for x in self.days.split(",") if x.strip().isdigit()}


class Room(TimeStamped, BranchOwned):
    name = models.CharField(max_length=60)
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    kind = models.CharField(max_length=30, blank=True, help_text="Classroom, lab, hall …")

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="timetable_room_name_unique")]

    def __str__(self) -> str:
        return self.name


class TeacherLoad(TimeStamped, BranchOwned):
    staff = models.OneToOneField("people.Staff", on_delete=models.CASCADE, related_name="teacher_load")
    max_periods_per_week = models.PositiveSmallIntegerField(default=DEFAULT_MAX_PERIODS)


class TimetableEntry(TimeStamped, BranchOwned):
    section = models.ForeignKey("people.Section", on_delete=models.CASCADE, related_name="timetable_entries")
    day = models.PositiveSmallIntegerField(choices=[(i, d) for i, d in enumerate(WEEKDAYS)])
    slot = models.ForeignKey(PeriodSlot, on_delete=models.CASCADE, related_name="entries")
    assignment = models.ForeignKey("people.TeachingAssignment", on_delete=models.CASCADE, related_name="timetable_entries")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")

    class Meta:
        ordering = ("section", "day", "slot__number")
        constraints = [models.UniqueConstraint(fields=["section", "day", "slot"], name="timetable_section_slot_once")]


class TeacherAbsence(TimeStamped, BranchOwned):
    """A teacher away on a date (entered by the office; HR leave adds these from M4)."""

    staff = models.ForeignKey("people.Staff", on_delete=models.CASCADE, related_name="absences")
    date = models.DateField()
    reason = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("-date",)
        constraints = [models.UniqueConstraint(fields=["staff", "date"], name="timetable_absence_once_per_day")]


class Substitution(TimeStamped, BranchOwned):
    date = models.DateField()
    entry = models.ForeignKey(TimetableEntry, on_delete=models.CASCADE, related_name="substitutions")
    absent_staff = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="+")
    substitute = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="substitutions")
    confirmed_by = models.CharField(max_length=255)
    note = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("-date", "entry__slot__number")
        constraints = [models.UniqueConstraint(fields=["entry", "date"], name="timetable_one_substitute_per_period")]

"""Clash-checked timetable building, views and substitution (ADR-008).

Clashes are checked by *time overlap* on the same weekday, so sections on
different bell schedules are compared correctly.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, time

from django.db import transaction
from django.db.models import Q

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.people.models import Section, Staff, TeachingAssignment
from apps.timetable.models import (
    DEFAULT_MAX_PERIODS, WEEKDAYS, BellSchedule, PeriodSlot, Room, Substitution, TeacherAbsence, TeacherLoad, TimetableEntry,
)


def schedule_for(section: Section) -> BellSchedule | None:
    return (BellSchedule.objects.filter(sections=section).first()
            or BellSchedule.objects.filter(branch=section.branch, is_default=True).first())


def _overlaps(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return a_start < b_end and b_start < a_end


def _busy(entries, slot: PeriodSlot, exclude_pk=None):
    for e in entries:
        if e.pk != exclude_pk and _overlaps(e.slot.start, e.slot.end, slot.start, slot.end):
            return e
    return None


def max_periods(staff: Staff) -> int:
    load = TeacherLoad.objects.filter(staff=staff).first()
    return load.max_periods_per_week if load else DEFAULT_MAX_PERIODS


def label(entry: TimetableEntry) -> str:
    return f"{entry.section} {WEEKDAYS[entry.day]} {entry.slot.label}"


@transaction.atomic
def place(*, section: Section, day: int, slot: PeriodSlot, assignment: TeachingAssignment, room: Room | None = None,
          entry: TimetableEntry | None = None, by: str = "") -> TimetableEntry:
    """Put a period on the grid (or move/change `entry`). Refused on any clash."""
    if assignment.section_id != section.pk:
        raise Conflict("That teacher and subject are allocated to another section.")
    schedule = schedule_for(section)
    if schedule is None or slot.schedule_id != schedule.pk:
        raise Conflict("That period is not on this section's bell schedule.")
    if slot.is_break:
        raise Conflict(f"{slot.label} is a break.")
    if day not in slot.weekdays:
        raise Conflict(f"{slot.label} does not run on {WEEKDAYS[day]}.")
    # lock the teacher's row so two offices can't double-book at once
    staff = Staff.objects.select_for_update().get(pk=assignment.staff_id)
    exclude = entry.pk if entry else None

    taken = TimetableEntry.objects.filter(section=section, day=day, slot=slot).exclude(pk=exclude).first()
    if taken:
        raise Conflict(f"{section} already has {taken.assignment.subject.name} in {slot.label} on {WEEKDAYS[day]}.")
    teacher_day = list(TimetableEntry.objects.filter(assignment__staff=staff, day=day).select_related("slot", "section"))
    clash = _busy(teacher_day, slot, exclude)
    if clash:
        raise Conflict(f"{staff.full_name} already teaches {clash.section} in {clash.slot.label} "
                       f"({clash.slot.start:%H:%M}–{clash.slot.end:%H:%M}) on {WEEKDAYS[day]}.")
    if room is not None:
        room_day = list(TimetableEntry.objects.filter(room=room, day=day).select_related("slot", "section"))
        clash = _busy(room_day, slot, exclude)
        if clash:
            raise Conflict(f"{room} is booked by {clash.section} in {clash.slot.label} on {WEEKDAYS[day]}.")
    week = TimetableEntry.objects.filter(assignment__staff=staff).exclude(pk=exclude).count()
    if week >= max_periods(staff):
        raise Conflict(f"{staff.full_name} already has {week} periods a week (limit {max_periods(staff)}).")
    if assignment.periods_per_week:
        used = TimetableEntry.objects.filter(assignment=assignment).exclude(pk=exclude).count()
        if used >= assignment.periods_per_week:
            raise Conflict(f"{assignment.subject.name} for {section} already has its {assignment.periods_per_week} periods a week.")

    if entry is None:
        entry = TimetableEntry.objects.create(branch=section.branch, section=section, day=day, slot=slot,
                                              assignment=assignment, room=room)
    else:
        entry.section, entry.day, entry.slot, entry.assignment, entry.room = section, day, slot, assignment, room
        entry.save()
    record("timetable.placed", actor=by, entry=entry.pk, section=section.pk, day=day, slot=slot.pk, staff=staff.pk)
    return entry


# ------------------------------------------------------------------ views
def _cell(e: TimetableEntry, sub: Substitution | None = None) -> dict:
    return {
        "entry": e.pk, "section": e.section_id, "section_name": str(e.section), "subject": e.assignment.subject.name,
        "teacher": e.assignment.staff_id, "teacher_name": e.assignment.staff.full_name,
        "room": e.room.name if e.room else None,
        "substitute": sub.substitute_id if sub else None, "substitute_name": sub.substitute.full_name if sub else None,
    }


def _entries(**filters):
    return TimetableEntry.objects.filter(**filters).select_related(
        "slot", "section__program", "assignment__subject", "assignment__staff", "room")


def section_grid(section: Section, on: date | None = None) -> dict:
    schedule = schedule_for(section)
    slots = list(schedule.slots.all()) if schedule else []
    subs = {}
    if on is not None:
        subs = {s.entry_id: s for s in Substitution.objects.filter(date=on, entry__section=section).select_related("substitute")}
    cells = {(e.day, e.slot_id): _cell(e, subs.get(e.pk) if on and e.day == on.weekday() else None)
             for e in _entries(section=section)}
    days = sorted({d for s in slots for d in s.weekdays})
    return {
        "title": str(section), "kind": "section", "schedule": schedule.name if schedule else None,
        "days": [{"day": d, "name": WEEKDAYS[d]} for d in days],
        "slots": [{"slot": s.pk, "number": s.number, "label": s.label, "start": s.start, "end": s.end, "is_break": s.is_break,
                   "days": sorted(s.weekdays)} for s in slots],
        "cells": [{"day": d, "slot": sid, **c} for (d, sid), c in cells.items()],
    }


def _by_time(entries, title: str, kind: str, extra=None) -> dict:
    """Teacher/room grid: rows are distinct time bands (they may come from several schedules)."""
    bands = sorted({(e.slot.start, e.slot.end, e.slot.label) for e in entries} | set(extra or []))
    index = {(b[0], b[1]): i for i, b in enumerate(bands)}
    cells = []
    for e in entries:
        cells.append({"day": e.day, "band": index[(e.slot.start, e.slot.end)], **_cell(e)})
    days = sorted({e.day for e in entries}) or list(range(6))
    return {"title": title, "kind": kind, "days": [{"day": d, "name": WEEKDAYS[d]} for d in days],
            "bands": [{"band": i, "start": b[0], "end": b[1], "label": b[2]} for i, b in enumerate(bands)], "cells": cells}


def teacher_grid(staff: Staff, on: date | None = None) -> dict:
    entries = list(_entries(assignment__staff=staff))
    grid = _by_time(entries, staff.full_name, "teacher")
    if on is not None:  # that date's substitutions: covering for others, and own periods given away
        for s in Substitution.objects.filter(date=on).filter(Q(substitute=staff) | Q(absent_staff=staff)).select_related(
                "entry__slot", "entry__section", "entry__assignment__subject", "entry__assignment__staff", "substitute"):
            grid.setdefault("substitutions", []).append({
                "date": on, "entry": s.entry_id, "section_name": str(s.entry.section), "slot": s.entry.slot.label,
                "start": s.entry.slot.start, "end": s.entry.slot.end, "subject": s.entry.assignment.subject.name,
                "covering_for": s.absent_staff.full_name if s.substitute_id == staff.pk else None,
                "covered_by": s.substitute.full_name if s.absent_staff_id == staff.pk else None,
            })
    return grid


def room_grid(room: Room) -> dict:
    return _by_time(list(_entries(room=room)), room.name, "room")


# ------------------------------------------------------------------ substitution
def absent_on(branch, on: date) -> set[int]:
    ids = set(TeacherAbsence.objects.filter(branch=branch, date=on).values_list("staff_id", flat=True))
    try:  # HR leave (M4) also counts, once that module records approved leave
        from apps.hr.services import staff_on_leave  # type: ignore[attr-defined]

        ids |= set(staff_on_leave(branch=branch, on=on))
    except (ImportError, AttributeError):
        pass
    return ids


def periods_to_cover(*, branch, on: date) -> list[dict]:
    """Every period that day of every absent teacher, with any substitute already confirmed."""
    absent = absent_on(branch, on)
    subs = {s.entry_id: s for s in Substitution.objects.filter(date=on, branch=branch).select_related("substitute")}
    out = []
    for e in _entries(assignment__staff_id__in=absent, day=on.weekday(), branch=branch).order_by("slot__start"):
        s = subs.get(e.pk)
        out.append({**_cell(e), "slot": e.slot.label, "start": e.slot.start, "end": e.slot.end,
                    "substitute": s.substitute_id if s else None, "substitute_name": s.substitute.full_name if s else None})
    return out


def _teachers(branch):
    return Staff.objects.filter(branch=branch, status=Staff.Status.ACTIVE, deleted_at__isnull=True,
                                teaching_assignments__isnull=False).distinct()


def suggest(*, entry: TimetableEntry, on: date) -> list[dict]:
    """Free teachers for this period, same subject first, then fewest periods that day."""
    if entry.day != on.weekday():
        raise Conflict("That period is not on this date's weekday.")
    branch, slot = entry.branch, entry.slot
    absent = absent_on(branch, on)
    day_entries = defaultdict(list)
    for e in _entries(day=entry.day, branch=branch):
        day_entries[e.assignment.staff_id].append(e)
    covering = defaultdict(list)
    for s in Substitution.objects.filter(date=on, branch=branch).select_related("entry__slot"):
        covering[s.substitute_id].append(s.entry)
    subject_teachers = set(TeachingAssignment.objects.filter(subject__name=entry.assignment.subject.name,
                                                             branch=branch).values_list("staff_id", flat=True))
    out = []
    for t in _teachers(branch):
        if t.pk in absent or t.pk == entry.assignment.staff_id:
            continue
        if _busy(day_entries[t.pk], slot) or _busy(covering[t.pk], slot):
            continue
        out.append({"staff": t.pk, "name": t.full_name, "same_subject": t.pk in subject_teachers,
                    "periods_that_day": len(day_entries[t.pk]) + len(covering[t.pk])})
    return sorted(out, key=lambda r: (not r["same_subject"], r["periods_that_day"], r["name"]))


@transaction.atomic
def confirm(*, entry: TimetableEntry, on: date, substitute: Staff, by: str, note: str = "") -> Substitution:
    if substitute.pk not in {c["staff"] for c in suggest(entry=entry, on=on)}:
        raise Conflict(f"{substitute.full_name} is not free for {entry.slot.label} on {on:%d-%m-%Y}.")
    sub, _ = Substitution.objects.update_or_create(
        entry=entry, date=on,
        defaults={"branch": entry.branch, "absent_staff": entry.assignment.staff, "substitute": substitute,
                  "confirmed_by": by, "note": note},
    )
    record("timetable.substitution", actor=by, entry=entry.pk, date=str(on), substitute=substitute.pk)
    return sub


def register(*, branch, start: date, end: date) -> dict:
    subs = list(Substitution.objects.filter(branch=branch, date__range=(start, end)).select_related(
        "entry__slot", "entry__section__program", "entry__assignment__subject", "absent_staff", "substitute"))
    counts = defaultdict(int)
    for s in subs:
        counts[(s.substitute_id, s.substitute.full_name)] += 1
    return {
        "from": start, "to": end,
        "rows": [{"date": s.date, "section_name": str(s.entry.section), "slot": s.entry.slot.label,
                  "subject": s.entry.assignment.subject.name, "absent": s.absent_staff.full_name,
                  "substitute": s.substitute.full_name, "confirmed_by": s.confirmed_by} for s in subs],
        "per_teacher": [{"staff": k[0], "name": k[1], "periods": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])],
    }

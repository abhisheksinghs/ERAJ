"""Attendance marking, corrections, percentages and punch ingestion (ADR-008)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.attendance.models import AttendanceCard, AttendanceDevice, AttendanceRecord, AttendanceSettings, Holiday, Punch
from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.people.models import Enrollment, Section, TeachingAssignment

# Late and half-day count as attended for the percentage; half-day counts half.
WEIGHT = {"present": 1.0, "late": 1.0, "half_day": 0.5}
CODE = {"present": "P", "absent": "A", "leave": "L", "late": "LT", "half_day": "H"}


def settings_for(branch) -> AttendanceSettings:
    obj, _ = AttendanceSettings.objects.get_or_create(branch=branch)
    return obj


# ------------------------------------------------------------------ calendar
def non_working_days(branch, start: date, end: date) -> dict[date, str]:
    """Holiday name (or "Sunday" etc.) for every non-working day in range."""
    out = {h.date: h.name for h in Holiday.objects.filter(branch=branch, date__range=(start, end))}
    offs = settings_for(branch).weekly_off_days
    d = start
    while d <= end:
        if d.weekday() in offs and d not in out:
            out[d] = d.strftime("%A")
        d += timedelta(days=1)
    return out


def section_students(section: Section):
    """Active students of a section, in roll order."""
    return [
        e.student for e in Enrollment.objects.filter(section=section, status=Enrollment.Status.ACTIVE)
        .select_related("student").order_by("roll_no", "student__full_name")
        if e.student.status == "active"
    ]


# ------------------------------------------------------------------ who may mark
def may_mark_section(*, staff, section: Section, subject=None) -> bool:
    """A teacher marks their own class (class teacher) or a section they teach
    (the subject, in per-lecture mode)."""
    if staff is None:
        return False
    if section.class_teacher_id == staff.pk:
        return True
    qs = TeachingAssignment.objects.filter(staff=staff, section=section)
    if subject is not None:
        qs = qs.filter(subject=subject)
    return qs.exists()


# ------------------------------------------------------------------ marking
@dataclass
class MarkResult:
    created: int
    updated: int
    unchanged: int


@transaction.atomic
def mark_section(*, section: Section, on: date, statuses: dict[int, str], absent: list[int] | None = None,
                 period: int | None = None, subject=None, by: str, can_correct_past: bool) -> MarkResult:
    """One save for a whole section: everyone present unless listed in
    `absent` or given another status in `statuses` ({student_id: status})."""
    if on > timezone.localdate():
        raise Conflict("Attendance cannot be marked for a future date.")
    holiday = non_working_days(section.branch, on, on).get(on)
    if holiday:
        raise Conflict(f"{on:%d-%m-%Y} is a holiday ({holiday}).")
    mode = settings_for(section.branch).mode
    if mode == AttendanceSettings.Mode.PER_LECTURE and period is None:
        raise Conflict("This institution marks attendance per lecture: choose the lecture.")
    if mode == AttendanceSettings.Mode.DAILY:
        period, subject = None, None

    students = section_students(section)
    ids = {s.pk for s in students}
    wanted = {sid: AttendanceRecord.Status.PRESENT for sid in ids}
    for sid in absent or []:
        wanted[int(sid)] = AttendanceRecord.Status.ABSENT
    for sid, st in (statuses or {}).items():
        wanted[int(sid)] = st
    stray = set(wanted) - ids
    if stray:
        raise Conflict(f"Not in this section: {sorted(stray)}")
    bad = {st for st in wanted.values() if st not in AttendanceRecord.Status.values}
    if bad:
        raise Conflict(f"Unknown status: {sorted(bad)}")

    existing = {
        r.student_id: r for r in AttendanceRecord.objects.select_for_update()
        .filter(student_id__in=ids, date=on, period=period)
    }
    past = on < timezone.localdate()
    changes = [(sid, existing[sid].status, st) for sid, st in wanted.items() if sid in existing and existing[sid].status != st]
    if past and changes and not can_correct_past:
        raise Conflict("Attendance for a past day can only be corrected by Admin.")

    created = updated = 0
    new_rows = []
    for sid, st in wanted.items():
        rec = existing.get(sid)
        if rec is None:
            new_rows.append(AttendanceRecord(branch=section.branch, student_id=sid, section=section, date=on, period=period,
                                             subject=subject, status=st, marked_by=by))
        elif rec.status != st:
            rec.status, rec.marked_by, rec.source, rec.section = st, by, AttendanceRecord.Source.MANUAL, section
            rec.save(update_fields=["status", "marked_by", "source", "section", "updated_at"])
            updated += 1
    AttendanceRecord.objects.bulk_create(new_rows)
    created = len(new_rows)
    if changes:
        record("attendance.corrected", actor=by, section=section.pk, date=str(on), period=period,
               changes=[{"student": s, "from": a, "to": b} for s, a, b in changes])
    record("attendance.marked", actor=by, section=section.pk, date=str(on), period=period,
           present=sum(1 for v in wanted.values() if v == "present"), total=len(wanted))
    return MarkResult(created=created, updated=updated, unchanged=len(wanted) - created - updated)


def sheet(*, section: Section, on: date, period: int | None = None) -> dict:
    """The teacher's marking sheet: every student with their saved status, or
    a suggestion from today's device punches."""
    students = section_students(section)
    saved = {r.student_id: r for r in AttendanceRecord.objects.filter(student__in=students, date=on, period=period)}
    punched = set(
        Punch.objects.filter(student__in=students, punched_at__date=on).values_list("student_id", flat=True)
    )
    enr = {e.student_id: e.roll_no for e in Enrollment.objects.filter(section=section, student__in=students)}
    return {
        "section": section.pk,
        "section_name": str(section),
        "date": on,
        "period": period,
        "holiday": non_working_days(section.branch, on, on).get(on),
        "mode": settings_for(section.branch).mode,
        "students": [
            {
                "student": s.pk, "name": s.full_name, "admission_no": s.admission_no, "roll_no": enr.get(s.pk, ""),
                "status": saved[s.pk].status if s.pk in saved else None,
                "source": saved[s.pk].source if s.pk in saved else None,
                "punched": s.pk in punched,
            }
            for s in students
        ],
    }


# ------------------------------------------------------------------ percentages
def percentage(records) -> tuple[float, int, float]:
    """(attended, marked, %) for an iterable of statuses."""
    statuses = list(records)
    attended = sum(WEIGHT.get(s, 0.0) for s in statuses)
    marked = len(statuses)
    return attended, marked, round(attended / marked * 100, 1) if marked else 0.0


def student_calendar(*, student, start: date, end: date) -> dict:
    off = non_working_days(student.branch, start, end)
    recs = AttendanceRecord.objects.filter(student=student, date__range=(start, end)).order_by("date", "period")
    by_day: dict[date, list[str]] = {}
    for r in recs:
        by_day.setdefault(r.date, []).append(r.status)
    days, counted = [], []
    d = start
    while d <= end:
        st = by_day.get(d, [])
        if d in off:
            days.append({"date": d, "holiday": off[d], "statuses": []})
        else:
            days.append({"date": d, "holiday": None, "statuses": st})
            counted.extend(st)
        d += timedelta(days=1)
    attended, marked, pct = percentage(counted)
    return {"student": student.pk, "from": start, "to": end, "days": days,
            "attended": attended, "marked": marked, "percentage": pct}


def section_percentages(*, section: Section, start: date, end: date) -> list[dict]:
    off = set(non_working_days(section.branch, start, end))
    students = section_students(section)
    rows = {s.pk: [] for s in students}
    for sid, d, st in AttendanceRecord.objects.filter(student__in=students, date__range=(start, end)).values_list("student_id", "date", "status"):
        if d not in off:
            rows[sid].append(st)
    out = []
    for s in students:
        attended, marked, pct = percentage(rows[s.pk])
        out.append({"student": s.pk, "name": s.full_name, "admission_no": s.admission_no, "section": str(section),
                    "attended": attended, "marked": marked, "percentage": pct})
    return out


# ------------------------------------------------------------------ punches
def _resolve(branch, code: str):
    card = AttendanceCard.objects.filter(branch=branch, code=code, is_active=True).first()
    return (card.student, card.staff) if card else (None, None)


@transaction.atomic
def ingest_punch(*, branch, code: str, at: datetime, device: AttendanceDevice | None, source: str) -> Punch | None:
    """Store one punch (duplicates ignored) and, in daily mode, mark the
    student present for that day unless a teacher already marked them."""
    code = str(code).strip()
    if not code:
        return None
    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    student, staff = _resolve(branch, code)
    try:
        with transaction.atomic():
            punch = Punch.objects.create(branch=branch, device=device, code=code, punched_at=at, student=student,
                                         staff=staff, source=source)
    except IntegrityError:
        return None
    if student is not None:
        cfg = settings_for(branch)
        day = timezone.localtime(at).date()
        if (cfg.mode == AttendanceSettings.Mode.DAILY and cfg.auto_mark_from_punches
                and day not in non_working_days(branch, day, day)):
            enr = Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE,
                                            academic_year__start_date__lte=day, academic_year__end_date__gte=day).first()
            AttendanceRecord.objects.get_or_create(
                student=student, date=day, period=None,
                defaults={"branch": branch, "section": enr.section if enr else None, "status": AttendanceRecord.Status.PRESENT,
                          "source": AttendanceRecord.Source.DEVICE, "marked_by": f"device:{device.serial_no if device else 'import'}"},
            )
    return punch


# ------------------------------------------------------------------ reports
def long_absentees(*, branch, as_of: date, min_days: int, section: Section | None = None) -> list[dict]:
    """Students whose most recent `min_days` marked working days are all absent."""
    start = as_of - timedelta(days=min_days * 3 + 14)
    off = set(non_working_days(branch, start, as_of))
    qs = AttendanceRecord.objects.filter(branch=branch, period=None, date__range=(start, as_of)).exclude(date__in=off)
    if section is not None:
        qs = qs.filter(section=section)
    by_student: dict[int, list[tuple[date, str]]] = {}
    for sid, d, st in qs.order_by("student_id", "-date").values_list("student_id", "date", "status"):
        by_student.setdefault(sid, []).append((d, st))
    out = []
    from apps.people.models import Student

    names = {s.pk: s for s in Student.objects.filter(pk__in=by_student)}
    for sid, rows in by_student.items():
        streak = 0
        for _, st in rows:
            if st != AttendanceRecord.Status.ABSENT:
                break
            streak += 1
        if streak >= min_days:
            out.append({"student": sid, "name": names[sid].full_name, "admission_no": names[sid].admission_no,
                        "absent_days": streak, "since": rows[streak - 1][0]})
    return sorted(out, key=lambda r: -r["absent_days"])


def daily_summary(*, branch, on: date) -> list[dict]:
    sections = Section.objects.filter(branch=branch, academic_year__start_date__lte=on, academic_year__end_date__gte=on)
    recs = AttendanceRecord.objects.filter(branch=branch, date=on, period=None)
    counts: dict[int, dict[str, int]] = {}
    for sec_id, st in recs.values_list("section_id", "status"):
        counts.setdefault(sec_id, {}).setdefault(st, 0)
        counts[sec_id][st] += 1
    out = []
    for sec in sections.select_related("program"):
        enrolled = Enrollment.objects.filter(section=sec, status=Enrollment.Status.ACTIVE).count()
        c = counts.get(sec.pk, {})
        marked = sum(c.values())
        attended, _, pct = percentage([s for s, n in c.items() for _ in range(n)])
        out.append({"section": sec.pk, "section_name": str(sec), "enrolled": enrolled, "marked": marked,
                    "present": c.get("present", 0), "absent": c.get("absent", 0), "leave": c.get("leave", 0),
                    "late": c.get("late", 0), "half_day": c.get("half_day", 0), "percentage": pct})
    return out


def register(*, section: Section, month: date) -> dict:
    """Monthly register: dates across, students down."""
    import calendar

    start = month.replace(day=1)
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    off = non_working_days(section.branch, start, end)
    students = section_students(section)
    enr = {e.student_id: e.roll_no for e in Enrollment.objects.filter(section=section, student__in=students)}
    marks: dict[int, dict[date, str]] = {s.pk: {} for s in students}
    for sid, d, st in AttendanceRecord.objects.filter(student__in=students, date__range=(start, end), period=None).values_list("student_id", "date", "status"):
        marks[sid][d] = st
    days = [{"date": start + timedelta(days=i), "holiday": off.get(start + timedelta(days=i))} for i in range((end - start).days + 1)]
    rows = []
    for s in students:
        counted = [st for d, st in marks[s.pk].items() if d not in off]
        attended, marked, pct = percentage(counted)
        rows.append({
            "student": s.pk, "name": s.full_name, "roll_no": enr.get(s.pk, ""),
            "marks": [None if day["holiday"] else CODE.get(marks[s.pk].get(day["date"])) for day in days],
            "attended": attended, "marked": marked, "percentage": pct,
        })
    return {"section": section.pk, "section_name": str(section), "month": start, "days": days, "rows": rows,
            "working_days": sum(1 for d in days if not d["holiday"])}


def staff_in_scope_filter(staff) -> Q:
    """Sections a teacher may see/mark."""
    return Q(class_teacher=staff) | Q(teaching_assignments__staff=staff)

"""HR business rules (ADR-009): staff attendance, leave, exit.

All writes are atomic and audited; rule violations raise `Conflict` (HTTP 409).
A month whose payroll is locked cannot have its attendance or leave changed.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.hr.models import LeaveApplication, LeaveBalance, LeaveType, StaffAttendance, StaffProfile
from apps.people.models import Staff

S = StaffAttendance.Status
ZERO = Decimal("0")
HALF = Decimal("0.5")
CODE = {"present": "P", "absent": "A", "leave": "L", "half_day": "H", "on_duty": "OD"}


# ------------------------------------------------------------------ calendar
def non_working_days(branch, start: date, end: date) -> dict[date, str]:
    from apps.attendance.services import non_working_days as nwd

    return nwd(branch, start, end)


def working_days(branch, start: date, end: date) -> list[date]:
    off = non_working_days(branch, start, end)
    out, d = [], start
    while d <= end:
        if d not in off:
            out.append(d)
        d += timedelta(days=1)
    return out


def month_bounds(month: date) -> tuple[date, date]:
    start = month.replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def guard_unlocked(branch, days) -> None:
    """Refuse changes to a month whose payroll is locked."""
    from apps.payroll.services import locked_months

    months = {d.replace(day=1) for d in days}
    locked = locked_months(branch=branch, months=months)
    if locked:
        m = min(locked)
        raise Conflict(f"Payroll for {m:%B %Y} is locked; attendance and leave for that month can't be changed.")


def active_staff(branch):
    return Staff.objects.filter(branch=branch, status=Staff.Status.ACTIVE)


# ------------------------------------------------------------------ attendance
@dataclass
class MarkResult:
    created: int
    updated: int
    unchanged: int
    skipped_leave: int


@transaction.atomic
def mark_day(*, branch, on: date, statuses: dict[int, str] | None = None, absent: list[int] | None = None,
             by: str, can_correct_past: bool) -> MarkResult:
    """One save for the whole staff: everyone active is present unless listed
    in `absent` or given another status. Days covered by approved leave keep
    the leave mark."""
    if on > timezone.localdate():
        raise Conflict("Staff attendance cannot be marked for a future date.")
    holiday = non_working_days(branch, on, on).get(on)
    if holiday:
        raise Conflict(f"{on:%d-%m-%Y} is a holiday ({holiday}).")
    guard_unlocked(branch, [on])
    wanted = {int(k): v for k, v in (statuses or {}).items()}
    for sid in absent or []:
        wanted[int(sid)] = S.ABSENT
    bad = {v for v in wanted.values() if v not in {S.PRESENT, S.ABSENT, S.HALF_DAY, S.ON_DUTY}}
    if bad:
        raise Conflict(f"Use Leave applications for leave; unknown status: {', '.join(sorted(bad))}.")
    staff = list(active_staff(branch))
    known = {s.pk for s in staff}
    unknown = set(wanted) - known
    if unknown:
        raise Conflict("Some staff are not active staff of this branch.")
    existing = {a.staff_id: a for a in StaffAttendance.objects.select_for_update().filter(branch=branch, date=on)}
    created = updated = unchanged = skipped = 0
    for s in staff:
        status = wanted.get(s.pk, S.PRESENT)
        row = existing.get(s.pk)
        if row is None:
            StaffAttendance.objects.create(branch=branch, staff=s, date=on, status=status, marked_by=by)
            created += 1
        elif row.source == StaffAttendance.Source.LEAVE:
            skipped += 1
        elif row.status == status:
            unchanged += 1
        else:
            if on < timezone.localdate() and not can_correct_past:
                raise Conflict("Only Admin can change staff attendance already marked for a past date.")
            record("hr.attendance.corrected", actor=by, staff=s.pk, date=str(on), old=row.status, new=status)
            row.status, row.source, row.marked_by = status, StaffAttendance.Source.MANUAL, by
            row.save(update_fields=["status", "source", "marked_by", "updated_at"])
            updated += 1
    record("hr.attendance.marked", actor=by, branch=branch.pk, date=str(on), created=created, updated=updated)
    return MarkResult(created, updated, unchanged, skipped)


def mark_from_punch(*, staff, at: datetime) -> None:
    """First punch of a working day marks the staff member present (ADR-008 punches)."""
    day = timezone.localtime(at).date() if timezone.is_aware(at) else at.date()
    if staff.status != Staff.Status.ACTIVE or day in non_working_days(staff.branch, day, day):
        return
    try:
        guard_unlocked(staff.branch, [day])
    except Conflict:
        return
    StaffAttendance.objects.get_or_create(
        staff=staff, date=day,
        defaults={"branch": staff.branch, "status": S.PRESENT, "source": StaffAttendance.Source.DEVICE, "marked_by": "device"},
    )


def day_sheet(*, branch, on: date) -> dict:
    rows = {a.staff_id: a for a in StaffAttendance.objects.filter(branch=branch, date=on)}
    out = []
    for s in active_staff(branch).select_related("department"):
        a = rows.get(s.pk)
        out.append({"staff": s.pk, "name": s.full_name, "employee_code": s.employee_code, "designation": s.designation,
                    "department": s.department.name if s.department else "", "status": a.status if a else None,
                    "source": a.source if a else None, "locked_by_leave": bool(a and a.source == StaffAttendance.Source.LEAVE)})
    holiday = non_working_days(branch, on, on).get(on)
    return {"date": on, "holiday": holiday, "marked": bool(rows), "rows": out}


def lop_days(*, staff, start: date, end: date) -> Decimal:
    """Loss-of-pay days: absent 1, unexplained half-day ½, unpaid leave 1 (½ for a half-day application)."""
    total = ZERO
    for a in StaffAttendance.objects.filter(staff=staff, date__range=(start, end)).select_related("leave"):
        if a.status == S.ABSENT:
            total += 1
        elif a.status == S.HALF_DAY and a.leave_id is None:
            total += HALF
        elif a.unpaid:
            total += HALF if (a.leave and a.leave.half_day) else 1
    return total


def staff_on_leave(*, branch, on: date) -> list[int]:
    """Staff with approved leave (or marked on leave) that day — feeds timetable substitution."""
    ids = set(StaffAttendance.objects.filter(branch=branch, date=on, status=S.LEAVE).values_list("staff_id", flat=True))
    ids |= set(LeaveApplication.objects.filter(branch=branch, status=LeaveApplication.Status.APPROVED,
                                               start__lte=on, end__gte=on).values_list("staff_id", flat=True))
    return sorted(ids)


# ------------------------------------------------------------------ leave
def balance_for(*, staff, leave_type: LeaveType, year: int, lock: bool = False) -> LeaveBalance:
    qs = LeaveBalance.objects.select_for_update() if lock else LeaveBalance.objects
    bal = qs.filter(staff=staff, leave_type=leave_type, year=year).first()
    if bal is None:
        bal, _ = LeaveBalance.objects.get_or_create(
            staff=staff, leave_type=leave_type, year=year,
            defaults={"branch": staff.branch, "entitled": leave_type.annual_days or ZERO})
        if lock:
            bal = LeaveBalance.objects.select_for_update().get(pk=bal.pk)
    return bal


def pending_days(*, staff, leave_type, year: int, exclude=None) -> Decimal:
    qs = LeaveApplication.objects.filter(staff=staff, leave_type=leave_type, status=LeaveApplication.Status.PENDING,
                                         start__year=year)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.aggregate(t=Sum("days"))["t"] or ZERO


def available(*, balance: LeaveBalance, exclude=None) -> Decimal:
    return balance.entitled - balance.used - pending_days(staff=balance.staff, leave_type=balance.leave_type,
                                                          year=balance.year, exclude=exclude)


def _fmt(d: Decimal) -> str:
    return f"{d.normalize():f}" if d == d.to_integral() else f"{d:f}"


@transaction.atomic
def apply_leave(*, staff, leave_type: LeaveType, start: date, end: date, half_day: bool = False, reason: str = "",
                by: str) -> LeaveApplication:
    if not Staff.objects.filter(pk=staff.pk, status=Staff.Status.ACTIVE).exists():
        raise Conflict(f"{staff.full_name} has left; leave can't be applied.")
    if leave_type.branch_id != staff.branch_id:
        raise Conflict("That leave type belongs to another branch.")
    if end < start:
        raise Conflict("The leave ends before it starts.")
    if start.year != end.year:
        raise Conflict("Leave across two calendar years: apply separately for each year.")
    if half_day and (start != end or not leave_type.allow_half_day):
        raise Conflict("Half-day leave is for a single day of a leave type that allows it.")
    days_list = working_days(staff.branch, start, end)
    if not days_list:
        raise Conflict("Those dates are all holidays or weekly offs.")
    days = HALF if half_day else Decimal(len(days_list))
    clash = LeaveApplication.objects.filter(
        staff=staff, status__in=[LeaveApplication.Status.PENDING, LeaveApplication.Status.APPROVED],
        start__lte=end, end__gte=start).first()
    if clash:
        raise Conflict(f"Overlaps {clash.leave_type.code} leave {clash.start:%d-%m-%Y}–{clash.end:%d-%m-%Y} ({clash.status}).")
    guard_unlocked(staff.branch, days_list)
    if leave_type.limited:
        bal = balance_for(staff=staff, leave_type=leave_type, year=start.year, lock=True)
        left = available(balance=bal)
        if days > left:
            raise Conflict(f"Only {_fmt(left)} day(s) of {leave_type.code} left for {start.year}; "
                           f"{_fmt(days)} requested.")
    app = LeaveApplication.objects.create(branch=staff.branch, staff=staff, leave_type=leave_type, start=start, end=end,
                                          half_day=half_day, days=days, reason=reason, applied_by=by)
    record("hr.leave.applied", actor=by, application=app.pk, staff=staff.pk, type=leave_type.code, days=str(days))
    return app


def _locked_app(app: LeaveApplication) -> LeaveApplication:
    return LeaveApplication.objects.select_for_update().select_related("leave_type", "staff__branch").get(pk=app.pk)


@transaction.atomic
def approve_leave(*, application: LeaveApplication, by: str, remarks: str = "") -> LeaveApplication:
    app = _locked_app(application)
    if app.status != LeaveApplication.Status.PENDING:
        raise Conflict(f"This application is already {app.status}.")
    days_list = working_days(app.staff.branch, app.start, app.end)
    guard_unlocked(app.branch, days_list)
    lt = app.leave_type
    if lt.limited:
        bal = balance_for(staff=app.staff, leave_type=lt, year=app.start.year, lock=True)
        left = available(balance=bal, exclude=app)
        if app.days > left:
            raise Conflict(f"Only {_fmt(left)} day(s) of {lt.code} left; can't approve {_fmt(app.days)}.")
        bal.used += app.days
        bal.save(update_fields=["used", "updated_at"])
    elif not lt.paid:
        balance_for(staff=app.staff, leave_type=lt, year=app.start.year)  # tracks LWP taken
        LeaveBalance.objects.filter(staff=app.staff, leave_type=lt, year=app.start.year).update(
            used=F("used") + app.days)
    for d in days_list:
        StaffAttendance.objects.update_or_create(
            staff=app.staff, date=d,
            defaults={"branch": app.branch, "status": S.LEAVE, "source": StaffAttendance.Source.LEAVE, "leave": app,
                      "unpaid": not lt.paid, "marked_by": by})
    app.status, app.decided_by, app.decided_at, app.remarks = LeaveApplication.Status.APPROVED, by, timezone.now(), remarks
    app.save(update_fields=["status", "decided_by", "decided_at", "remarks", "updated_at"])
    record("hr.leave.approved", actor=by, application=app.pk, staff=app.staff_id, days=str(app.days))
    return app


@transaction.atomic
def reject_leave(*, application: LeaveApplication, by: str, remarks: str = "") -> LeaveApplication:
    app = _locked_app(application)
    if app.status != LeaveApplication.Status.PENDING:
        raise Conflict(f"This application is already {app.status}.")
    if not remarks.strip():
        raise Conflict("Give a reason for rejecting.")
    app.status, app.decided_by, app.decided_at, app.remarks = LeaveApplication.Status.REJECTED, by, timezone.now(), remarks
    app.save(update_fields=["status", "decided_by", "decided_at", "remarks", "updated_at"])
    record("hr.leave.rejected", actor=by, application=app.pk, reason=remarks)
    return app


@transaction.atomic
def cancel_leave(*, application: LeaveApplication, by: str, may_cancel_approved: bool) -> LeaveApplication:
    app = _locked_app(application)
    if app.status == LeaveApplication.Status.PENDING:
        pass
    elif app.status == LeaveApplication.Status.APPROVED:
        if not may_cancel_approved:
            raise Conflict("Approved leave can be cancelled only by HR or Admin.")
        days = list(app.attendance_days.all().values_list("date", flat=True))
        guard_unlocked(app.branch, days or [app.start])
        lt = app.leave_type
        if lt.limited or not lt.paid:
            LeaveBalance.objects.filter(staff=app.staff, leave_type=lt, year=app.start.year).update(
                used=F("used") - app.days)
        app.attendance_days.all().delete()
    else:
        raise Conflict(f"This application is already {app.status}.")
    app.status = LeaveApplication.Status.CANCELLED
    app.decided_by, app.decided_at = by, timezone.now()
    app.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    record("hr.leave.cancelled", actor=by, application=app.pk)
    return app


@transaction.atomic
def open_year(*, branch, year: int, by: str) -> int:
    """Create every active staff member's balances for `year`, carrying forward
    unused days up to each type's limit. Existing balances are left alone."""
    n = 0
    types = list(LeaveType.objects.filter(branch=branch, annual_days__isnull=False))
    for s in active_staff(branch):
        for lt in types:
            if LeaveBalance.objects.filter(staff=s, leave_type=lt, year=year).exists():
                continue
            carry = ZERO
            prev = LeaveBalance.objects.filter(staff=s, leave_type=lt, year=year - 1).first()
            if prev and lt.max_carry_forward:
                carry = max(ZERO, min(lt.max_carry_forward, prev.entitled - prev.used))
            LeaveBalance.objects.create(branch=branch, staff=s, leave_type=lt, year=year, entitled=lt.annual_days + carry)
            n += 1
    record("hr.leave.year_opened", actor=by, branch=branch.pk, year=year, balances=n)
    return n


# ------------------------------------------------------------------ joining / exit
@transaction.atomic
def exit_staff(*, staff, relieved_on: date, reason: str, by: str) -> Staff:
    staff = Staff.objects.select_for_update().get(pk=staff.pk)
    if staff.status == Staff.Status.LEFT:
        raise Conflict(f"{staff.full_name} is already marked as left.")
    if not reason.strip():
        raise Conflict("Give the reason for leaving.")
    if relieved_on < staff.date_joined:
        raise Conflict("The relieving date is before the joining date.")
    profile, _ = StaffProfile.objects.get_or_create(staff=staff, defaults={"branch": staff.branch})
    profile.relieved_on, profile.exit_reason = relieved_on, reason
    profile.save(update_fields=["relieved_on", "exit_reason", "updated_at"])
    for app in LeaveApplication.objects.filter(staff=staff, status=LeaveApplication.Status.PENDING):
        app.status, app.decided_by, app.decided_at, app.remarks = (
            LeaveApplication.Status.CANCELLED, by, timezone.now(), "Staff member left")
        app.save(update_fields=["status", "decided_by", "decided_at", "remarks", "updated_at"])
    staff.status = Staff.Status.LEFT
    staff.save(update_fields=["status", "updated_at"])
    record("hr.staff.exited", actor=by, staff=staff.pk, relieved_on=str(relieved_on), reason=reason)
    return staff


# ------------------------------------------------------------------ reports
def register(*, branch, month: date, department=None) -> dict:
    start, end = month_bounds(month)
    off = non_working_days(branch, start, end)
    staff = active_staff(branch).select_related("department")
    if department is not None:
        staff = staff.filter(department=department)
    staff = list(staff)
    marks: dict[int, dict[date, StaffAttendance]] = {s.pk: {} for s in staff}
    for a in StaffAttendance.objects.filter(staff__in=staff, date__range=(start, end)).select_related("leave__leave_type"):
        marks[a.staff_id][a.date] = a
    days = [{"date": start + timedelta(days=i), "holiday": off.get(start + timedelta(days=i))}
            for i in range((end - start).days + 1)]
    rows = []
    for s in staff:
        m = marks[s.pk]
        counts = {k: 0 for k in CODE}
        for d, a in m.items():
            if d not in off:
                counts[a.status] += 1
        cells = []
        for day in days:
            a = m.get(day["date"])
            if day["holiday"]:
                cells.append(None)
            elif a is None:
                cells.append("")
            elif a.status == S.LEAVE and a.leave_id:
                cells.append(a.leave.leave_type.code)
            else:
                cells.append(CODE[a.status])
        rows.append({"staff": s.pk, "name": s.full_name, "employee_code": s.employee_code,
                     "department": s.department.name if s.department else "", "marks": cells, **counts,
                     "lop_days": lop_days(staff=s, start=start, end=end)})
    return {"month": start, "days": days, "rows": rows, "working_days": sum(1 for d in days if not d["holiday"])}


def headcount(*, branch) -> list[dict]:
    from collections import Counter

    c = Counter()
    for dept, etype in active_staff(branch).values_list("department__name", "employment_type"):
        c[(dept or "No department", etype)] += 1
    out: dict[str, dict] = {}
    for (dept, etype), n in c.items():
        row = out.setdefault(dept, {"department": dept, "permanent": 0, "contract": 0, "part_time": 0, "total": 0})
        row[etype] += n
        row["total"] += n
    return sorted(out.values(), key=lambda r: r["department"])


def balances_report(*, branch, year: int) -> list[dict]:
    rows = []
    for b in (LeaveBalance.objects.filter(branch=branch, year=year, staff__status=Staff.Status.ACTIVE)
              .select_related("staff", "leave_type").order_by("staff__full_name", "leave_type__code")):
        pend = pending_days(staff=b.staff, leave_type=b.leave_type, year=year)
        rows.append({"staff": b.staff_id, "name": b.staff.full_name, "employee_code": b.staff.employee_code,
                     "leave_type": b.leave_type.code, "entitled": b.entitled, "used": b.used, "pending": pend,
                     "available": b.entitled - b.used - pend})
    return rows


def absentees(*, branch, on: date) -> dict:
    rows = {a.staff_id: a for a in StaffAttendance.objects.filter(branch=branch, date=on).select_related("leave__leave_type")}
    away, unmarked = [], []
    for s in active_staff(branch).select_related("department"):
        a = rows.get(s.pk)
        base = {"staff": s.pk, "name": s.full_name, "employee_code": s.employee_code,
                "department": s.department.name if s.department else ""}
        if a is None:
            unmarked.append(base)
        elif a.status in (S.ABSENT, S.LEAVE, S.HALF_DAY):
            away.append({**base, "status": a.status, "leave_type": a.leave.leave_type.code if a.leave_id else ""})
    return {"date": on, "holiday": non_working_days(branch, on, on).get(on), "away": away, "not_marked": unmarked}


def directory_filter(params) -> Q:
    """Default staff lists to active staff (left staff stay in history)."""
    status = params.get("status")
    if status in (None, ""):
        return Q(status=Staff.Status.ACTIVE)
    if status == "all":
        return Q()
    return Q(status=status)

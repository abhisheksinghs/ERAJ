"""Mess: enrolment, leave, billing, guest meals, headcount, contractor bill (ADR-007).

Billing rules
  monthly plan  — month M billed in advance: monthly charge × (days enrolled in M /
                  days in M) − rebate for qualifying leave taken in M−1.
  per-day plan  — month M billed in arrears (on the 1st of M+1): per-day rate ×
                  (days enrolled in M − days on leave in M).
  A leave qualifies for the rebate when its whole length is at least the mess's
  minimum; the rebate is rebate/day × its days that fall in M−1.
Every charge is idempotent per member-month (`mess:<member>:<YYYY-MM>`).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.core.licensing import tenant_has_module
from apps.hostel.dates import add_months, days, days_in_month, month_end, month_start, overlap
from apps.hostel.models import GuestMeal, MealCount, Meal, Mess, MessLeave, MessMember, MessRebate

CENT = Decimal("0.01")
DUE_DAY = 10


def _money(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ members
@transaction.atomic
def enrol(*, mess: Mess, plan: str = MessMember.Plan.MONTHLY, start: date | None = None, student=None, staff=None,
          allocation=None) -> MessMember:
    if (student is None) == (staff is None):
        raise Conflict("Enrol either a student or a staff member.")
    person = student or staff
    if person.branch_id != mess.branch_id:
        raise Conflict("Member and mess belong to different branches.")
    open_q = MessMember.objects.filter(end_date__isnull=True)
    if (student and open_q.filter(student=student).exists()) or (staff and open_q.filter(staff=staff).exists()):
        raise Conflict("Already a member of a mess.")
    member = MessMember.objects.create(
        branch=mess.branch, mess=mess, student=student, staff=staff, plan=plan,
        start_date=start or timezone.localdate(), allocation=allocation,
    )
    if plan == MessMember.Plan.MONTHLY:
        bill_member_month(member, month_start(member.start_date))
    record("hostel.mess_enrol", detail={"member": member.pk, "mess": mess.pk, "plan": plan})
    return member


@transaction.atomic
def end_membership(*, member: MessMember, on: date | None = None) -> MessMember:
    if member.end_date:
        raise Conflict("Membership already ended.")
    on = on or timezone.localdate()
    if on < member.start_date:
        raise Conflict("End date is before the start date.")
    member.end_date = on
    member.save(update_fields=["end_date", "updated_at"])
    if member.student_id and tenant_has_module("fees"):
        from apps.fees import services as fees
        from apps.fees.models import Charge

        fees.cancel_future_charges(
            student=member.student, source_type=Charge.Source.MESS, source_prefix=f"mess:{member.pk}:",
            from_date=add_months(month_start(on), 1).replace(day=1), reason="Left the mess",
        )
    record("hostel.mess_end", detail={"member": member.pk, "on": str(on)})
    return member


@transaction.atomic
def record_leave(*, member: MessMember, from_date: date, to_date: date, reason: str = "", outpass=None) -> MessLeave:
    if to_date < from_date:
        raise Conflict("Leave ends before it starts.")
    if overlap(member.start_date, member.end_date, from_date, to_date) is None:
        raise Conflict("Leave falls outside the membership.")
    if member.leaves.filter(from_date__lte=to_date, to_date__gte=from_date).exists():
        raise Conflict("This member already has mess leave on some of these days.")
    return MessLeave.objects.create(
        branch=member.branch, member=member, from_date=from_date, to_date=to_date, reason=reason, outpass=outpass
    )


def _leave_dates(member: MessMember, start: date, end: date, *, qualifying_only: bool = False) -> dict[int, set[date]]:
    """Leave id → its dates within [start, end] and within the membership."""
    out: dict[int, set[date]] = {}
    span = overlap(member.start_date, member.end_date, start, end)
    if span is None:
        return out
    for leave in member.leaves.filter(from_date__lte=span[1], to_date__gte=span[0]):
        if qualifying_only and (member.mess.rebate_min_days == 0 or leave.days < member.mess.rebate_min_days):
            continue
        part = overlap(leave.from_date, leave.to_date, span[0], span[1])
        if part:
            out[leave.pk] = set(days(*part))
    return out


# ------------------------------------------------------------------ billing
@transaction.atomic
def bill_member_month(member: MessMember, month: date):
    """Post this member's mess charge for `month` (see module docstring).
    Returns the Charge, or None when nothing is owed / not billable here."""
    if member.student_id is None or not tenant_has_module("fees"):
        return None
    from apps.fees import services as fees
    from apps.fees.models import Charge, FeeHead

    mess = member.mess
    m0, m1 = month_start(month), month_end(month)
    span = overlap(member.start_date, member.end_date, m0, m1)
    if span is None:
        return None
    enrolled = (span[1] - span[0]).days + 1
    source_id = f"mess:{member.pk}:{m0:%Y-%m}"
    if Charge.objects.filter(student=member.student, source_type=Charge.Source.MESS, source_id=source_id,
                             cancelled_at__isnull=True).exists():
        return None

    if member.plan == MessMember.Plan.MONTHLY:
        base = _money(mess.monthly_charge * enrolled / days_in_month(m0))
        prev = add_months(m0, -1)
        # Rebates already worked out for last month belong to this bill (a re-run
        # after a zero bill must not forget them).
        rebates = list(MessRebate.objects.filter(member=member, month=prev))
        done = {r.leave_id for r in rebates}
        for leave_id, leave_days in _leave_dates(member, prev, month_end(prev), qualifying_only=True).items():
            if leave_id in done:
                continue
            rebates.append(MessRebate(
                branch=member.branch, member=member, leave_id=leave_id, month=prev, days=len(leave_days),
                amount=_money(mess.rebate_per_day * len(leave_days)),
            ))
        rebate_total = sum((r.amount for r in rebates), Decimal("0"))
        amount = max(base - rebate_total, Decimal("0"))
        note = f" (less {sum(r.days for r in rebates)} days' leave rebate ₹{rebate_total})" if rebates else ""
        description = f"Mess {mess.name} — {m0:%b %Y}{note}"
        due = max(m0.replace(day=DUE_DAY), member.start_date)
    else:
        leave_days = set().union(*_leave_dates(member, m0, m1).values()) if member.leaves.exists() else set()
        eaten = enrolled - len(leave_days)
        amount = _money(mess.per_day_rate * eaten)
        rebates = []
        description = f"Mess {mess.name} — {m0:%b %Y}: {eaten} days × ₹{mess.per_day_rate}"
        due = add_months(m0, 1).replace(day=DUE_DAY)

    charge = None
    if amount > 0:
        charge = fees.post_charge(
            student=member.student, amount=amount, kind=FeeHead.Kind.MESS, due_date=due, description=description,
            source_type=Charge.Source.MESS, source_id=source_id,
        )
    for r in rebates:
        r.charge = charge
        r.save()
    return charge


def bill_mess_month(*, branch, today: date | None = None) -> int:
    """Monthly job (1st of the month): monthly members for this month, per-day
    members for last month. Safe to re-run."""
    today = today or timezone.localdate()
    this_m, last_m = month_start(today), add_months(month_start(today), -1)
    n = 0
    members = MessMember.objects.filter(branch=branch, student__isnull=False).select_related("mess", "student")
    for member in members.filter(plan=MessMember.Plan.MONTHLY).filter(Q(end_date__isnull=True) | Q(end_date__gte=this_m)):
        n += bill_member_month(member, this_m) is not None
    for member in members.filter(plan=MessMember.Plan.PER_DAY).filter(Q(end_date__isnull=True) | Q(end_date__gte=last_m)):
        n += bill_member_month(member, last_m) is not None
    return n


# ------------------------------------------------------------------ guest meals
@transaction.atomic
def add_guest_meal(*, member: MessMember, meal: str, count: int = 1, on: date | None = None, guest_name: str = "") -> GuestMeal:
    on = on or timezone.localdate()
    if overlap(member.start_date, member.end_date, on, on) is None:
        raise Conflict("Not a mess member on that date.")
    amount = _money(member.mess.guest_meal_rate * count)
    gm = GuestMeal.objects.create(
        branch=member.branch, member=member, date=on, meal=meal, count=count, guest_name=guest_name, amount=amount
    )
    if member.student_id and amount > 0 and tenant_has_module("fees"):
        from apps.fees import services as fees
        from apps.fees.models import Charge, FeeHead

        gm.charge = fees.post_charge(
            student=member.student, amount=amount, kind=FeeHead.Kind.MESS, due_date=on,
            description=f"Guest meal — {Meal(meal).label} × {count} on {on:%d-%m-%Y}",
            source_type=Charge.Source.GUEST_MEAL, source_id=f"guest:{gm.pk}",
        )
        gm.save(update_fields=["charge", "updated_at"])
    return gm


# ------------------------------------------------------------------ headcount
def _members_on(mess: Mess, on: date):
    return MessMember.objects.filter(mess=mess, start_date__lte=on).filter(Q(end_date__isnull=True) | Q(end_date__gte=on))


def headcount(mess: Mess, on: date) -> dict:
    members = _members_on(mess, on)
    enrolled = members.count()
    on_leave = MessLeave.objects.filter(member__in=members, from_date__lte=on, to_date__gte=on).values("member").distinct().count()
    guests = dict(
        GuestMeal.objects.filter(member__mess=mess, date=on).values_list("meal").annotate(n=Sum("count")).values_list("meal", "n")
    )
    return {
        "date": on,
        "mess": mess.pk,
        "mess_name": mess.name,
        "enrolled": enrolled,
        "on_leave": on_leave,
        "meals": [
            {"meal": m.value, "label": m.label, "members": enrolled - on_leave, "guests": guests.get(m.value, 0),
             "expected": enrolled - on_leave + guests.get(m.value, 0)}
            for m in Meal
        ],
    }


def contractor_bill(mess: Mess, month: date) -> dict:
    """What the institution owes the contractor for `month`: plates × rate per
    meal. Plates come from the recorded MealCount, else the expected headcount."""
    m0, m1 = month_start(month), month_end(month)
    rates = {r.meal: r.rate for r in mess.meal_rates.all()}
    recorded = {(c.date, c.meal): c.served for c in MealCount.objects.filter(mess=mess, date__range=(m0, m1))}

    members = list(MessMember.objects.filter(mess=mess, start_date__lte=m1).filter(Q(end_date__isnull=True) | Q(end_date__gte=m0)))
    leaves = defaultdict(list)
    for lv in MessLeave.objects.filter(member__in=members, from_date__lte=m1, to_date__gte=m0):
        leaves[lv.member_id].append((lv.from_date, lv.to_date))
    guests = defaultdict(int)
    for g in GuestMeal.objects.filter(member__mess=mess, date__range=(m0, m1)):
        guests[(g.date, g.meal)] += g.count

    def expected(d: date) -> int:
        n = 0
        for mem in members:
            if mem.start_date <= d and (mem.end_date is None or mem.end_date >= d):
                if not any(f <= d <= t for f, t in leaves[mem.pk]):
                    n += 1
        return n

    rows, total = [], Decimal("0")
    per_day = {d: expected(d) for d in days(m0, m1)}
    for meal in Meal:
        if meal.value not in rates:
            continue
        plates = estimated_days = 0
        for d in days(m0, m1):
            if (d, meal.value) in recorded:
                plates += recorded[(d, meal.value)]
            else:
                plates += per_day[d] + guests[(d, meal.value)]
                estimated_days += 1
        amount = _money(rates[meal.value] * plates)
        total += amount
        rows.append({"meal": meal.value, "label": meal.label, "plates": plates, "rate": rates[meal.value],
                     "amount": amount, "estimated_days": estimated_days})
    return {"mess": mess.pk, "mess_name": mess.name, "contractor": mess.contractor_name, "month": m0,
            "rows": rows, "total": total}

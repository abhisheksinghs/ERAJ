"""
Fees ledger write paths (ADR-003). Every function here is atomic and takes the
row locks it needs; business-rule violations raise `Conflict` (HTTP 409).

Other modules call only `post_charge` and `cancel_future_charges`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.fees.models import (
    Charge,
    Concession,
    FeeHead,
    FeePlan,
    FeeSettings,
    Receipt,
    ReceiptCounter,
    ReceiptLine,
    Refund,
    RefundLine,
)
from apps.fees.selectors import charges_with_balance

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def financial_year(d: date) -> str:
    """Indian financial year (April–March): 2026-10-25 → "2026-27"."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def settings_for(branch) -> FeeSettings:
    obj, _ = FeeSettings.objects.get_or_create(branch=branch, defaults={"receipt_prefix": branch.code.upper()[:10]})
    return obj


def head_for_kind(branch, kind: str) -> FeeHead:
    """The head other modules post to (hostel, mess, transport, library fine …),
    created on first use so a branch needs no setup before its first charge."""
    head, _ = FeeHead.objects.get_or_create(
        branch=branch, code=kind.upper(), defaults={"name": FeeHead.Kind(kind).label, "kind": kind}
    )
    return head


# --------------------------------------------------------------------- charges
@transaction.atomic
def post_charge(
    *, student, amount, due_date: date, description: str, source_type: str, source_id: str = "",
    kind: str | None = None, head: FeeHead | None = None, academic_year=None, parent: Charge | None = None,
) -> Charge:
    """Add a charge to a student's account. Idempotent per (student,
    source_type, source_id): posting the same key twice returns the existing
    live charge instead of billing twice."""
    if head is None:
        if kind is None:
            raise ValueError("post_charge needs a head or a kind")
        head = head_for_kind(student.branch, kind)
    if head.branch_id != student.branch_id:
        raise Conflict("Fee head and student belong to different branches.")
    amount = money(amount)
    if amount < 0 and source_type != Charge.Source.MANUAL:
        raise Conflict("Only a manual adjustment can be negative.")
    if source_id:
        existing = Charge.objects.filter(
            student=student, source_type=source_type, source_id=source_id, cancelled_at__isnull=True
        ).first()
        if existing:
            return existing
    if academic_year is None:
        from apps.people.models import AcademicYear

        academic_year = AcademicYear.objects.filter(start_date__lte=due_date, end_date__gte=due_date).first()
    try:
        with transaction.atomic():
            charge = Charge.objects.create(
                branch=student.branch, student=student, head=head, academic_year=academic_year,
                description=description, due_date=due_date, amount=amount,
                source_type=source_type, source_id=source_id, parent=parent,
            )
    except IntegrityError:  # a concurrent post of the same key won the race
        return Charge.objects.get(
            student=student, source_type=source_type, source_id=source_id, cancelled_at__isnull=True
        )
    _recompute_discounts(student=student, head=head, academic_year=academic_year)
    charge.refresh_from_db()
    record("fees.charge_posted", detail={"charge": charge.pk, "student": student.pk, "amount": str(amount), "source": f"{source_type}:{source_id}"})
    return charge


@transaction.atomic
def cancel_future_charges(*, student, source_type: str, source_prefix: str, from_date: date, reason: str) -> int:
    """Cancel not-yet-paid charges of a source from `from_date` on (e.g. transport
    stopped from next month). Charges with any payment are left alone."""
    qs = charges_with_balance(
        Charge.objects.filter(
            student=student, source_type=source_type, source_id__startswith=source_prefix, due_date__gte=from_date
        )
    ).select_for_update(of=("self",))
    n = 0
    now = timezone.now()
    for charge in qs:
        if charge.received > 0:  # any money taken against it, even if since refunded
            continue
        Charge.objects.filter(pk=charge.pk).update(cancelled_at=now, cancel_reason=reason)
        n += 1
    if n:
        record("fees.charges_cancelled", detail={"student": student.pk, "source": f"{source_type}:{source_prefix}", "count": n})
    return n


@transaction.atomic
def cancel_charge(*, charge: Charge, reason: str) -> Charge:
    """Withdraw one charge (e.g. a library fine waived). Refused once any money
    has been taken against it — refund at the counter instead."""
    live = charges_with_balance(Charge.objects.filter(pk=charge.pk)).select_for_update(of=("self",)).first()
    if live is None:
        return charge  # already cancelled
    if live.received > 0:
        raise Conflict("This charge has already been paid at the fee counter; refund it there instead.")
    Charge.objects.filter(pk=charge.pk).update(cancelled_at=timezone.now(), cancel_reason=reason)
    _recompute_discounts(student=charge.student, head=charge.head, academic_year=charge.academic_year)
    record("fees.charge_cancelled", detail={"charge": charge.pk, "reason": reason})
    charge.refresh_from_db()
    return charge


@transaction.atomic
def add_adjustment(*, student, head: FeeHead, amount, description: str, due_date: date | None = None) -> Charge:
    """Manual charge (positive) or credit note (negative)."""
    return post_charge(
        student=student, head=head, amount=amount, due_date=due_date or timezone.localdate(),
        description=description, source_type=Charge.Source.MANUAL,
    )


# ----------------------------------------------------------------------- plans
def _plan_applies(plan: FeePlan, enrollment) -> bool:
    return (
        enrollment.academic_year_id == plan.academic_year_id
        and enrollment.program_id == plan.program_id
        and (plan.term_id is None or plan.term_id == enrollment.term_id)
    )


@transaction.atomic
def apply_plan_to_enrollment(plan: FeePlan, enrollment) -> int:
    if not _plan_applies(plan, enrollment):
        return 0
    n = 0
    for inst in plan.instalments.all():
        before = Charge.objects.filter(student=enrollment.student, source_type="plan", source_id=f"inst:{inst.pk}").exists()
        post_charge(
            student=enrollment.student, head=plan.head, amount=inst.amount, due_date=inst.due_date,
            description=f"{plan.head.name} — {inst.label}", source_type=Charge.Source.PLAN,
            source_id=f"inst:{inst.pk}", academic_year=plan.academic_year,
        )
        n += 0 if before else 1
    return n


@transaction.atomic
def apply_plan(plan: FeePlan) -> int:
    """Bill every active enrolment the plan covers. Safe to run again: existing
    instalment charges are not duplicated."""
    from apps.people.models import Enrollment

    enrollments = Enrollment.objects.filter(
        branch=plan.branch, academic_year=plan.academic_year, program=plan.program, status=Enrollment.Status.ACTIVE
    ).select_related("student")
    if plan.term_id:
        enrollments = enrollments.filter(term=plan.term)
    n = sum(apply_plan_to_enrollment(plan, e) for e in enrollments)
    record("fees.plan_applied", detail={"plan": plan.pk, "charges_created": n})
    return n


def apply_plans_for_enrollment(enrollment) -> int:
    plans = FeePlan.objects.filter(
        branch=enrollment.branch, academic_year=enrollment.academic_year, program=enrollment.program
    ).prefetch_related("instalments")
    return sum(apply_plan_to_enrollment(p, enrollment) for p in plans)


# ------------------------------------------------------------------ concessions
def _recompute_discounts(*, student, head: FeeHead, academic_year) -> None:
    approved = list(
        Concession.objects.filter(
            student=student, head=head, academic_year=academic_year, status=Concession.Status.APPROVED
        )
    )
    for charge in charges_with_balance(Charge.objects.filter(student=student, head=head, academic_year=academic_year)):
        if charge.amount <= 0:
            continue
        discount = ZERO
        for c in approved:
            discount += money(charge.amount * c.value / 100) if c.kind == Concession.Kind.PERCENT else money(c.value)
        # Never below what is already received: a late concession doesn't create
        # a credit (refund the difference instead, if the institution agrees).
        ceiling = max(ZERO, charge.amount - charge.received)
        discount = min(discount, ceiling)
        if discount != charge.discount:
            Charge.objects.filter(pk=charge.pk).update(discount=discount)


@transaction.atomic
def decide_concession(*, concession: Concession, approve: bool, by: str) -> Concession:
    concession = Concession.objects.select_for_update().get(pk=concession.pk)
    if concession.status != Concession.Status.PENDING:
        raise Conflict(f"Concession is already {concession.get_status_display().lower()}.")
    concession.status = Concession.Status.APPROVED if approve else Concession.Status.REJECTED
    concession.decided_by = by
    concession.decided_at = timezone.now()
    concession.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    if approve:
        _recompute_discounts(student=concession.student, head=concession.head, academic_year=concession.academic_year)
    record("fees.concession_" + ("approved" if approve else "rejected"), actor=by, detail={"concession": concession.pk})
    return concession


# ------------------------------------------------------------------- receipts
@dataclass
class LineIn:
    charge: Charge
    amount: Decimal


def _next_receipt_number(branch, on: date) -> tuple[str, str, int]:
    fy = financial_year(on)
    ReceiptCounter.objects.get_or_create(branch=branch, financial_year=fy)
    counter = ReceiptCounter.objects.select_for_update().get(branch=branch, financial_year=fy)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    prefix = settings_for(branch).receipt_prefix
    return f"{prefix}/{fy}/{counter.last_number:05d}", fy, counter.last_number


@transaction.atomic
def collect(
    *, student, mode: str, received_by: str, lines: list[LineIn] | None = None, amount=None,
    reference: str = "", on: date | None = None, note: str = "",
) -> Receipt:
    """Record a payment. Either explicit `lines` (charge + amount each), or an
    `amount` allocated to the oldest dues first."""
    on = on or timezone.localdate()
    if mode != Receipt.Mode.CASH and not reference:
        raise Conflict("A reference number is required for non-cash payments.")
    # Lock this student's live charges so two counters can't over-collect.
    list(Charge.objects.select_for_update().filter(student=student, cancelled_at__isnull=True).values_list("pk"))
    balances = {c.pk: c for c in charges_with_balance(Charge.objects.filter(student=student))}

    if lines is None:
        if amount is None:
            raise Conflict("Give either lines or an amount.")
        remaining = money(amount)
        if remaining <= 0:
            raise Conflict("Amount must be more than zero.")
        lines = []
        for c in sorted(balances.values(), key=lambda c: (c.due_date, c.pk)):
            if remaining <= 0:
                break
            if c.outstanding <= 0:
                continue
            take = min(c.outstanding, remaining)
            lines.append(LineIn(charge=c, amount=take))
            remaining -= take
        if remaining > 0:
            raise Conflict(f"Amount is more than the total due by ₹{remaining}.")

    if not lines:
        raise Conflict("Nothing to collect: no dues selected.")
    total = ZERO
    for line in lines:
        bal = balances.get(line.charge.pk)
        if bal is None or bal.student_id != student.pk:
            raise Conflict("A selected charge is not a live charge of this student.")
        amt = money(line.amount)
        if amt <= 0:
            raise Conflict("Each line must be more than zero.")
        if amt > bal.outstanding:
            raise Conflict(f"₹{amt} is more than the ₹{bal.outstanding} due on “{bal.description}”.")
        total += amt

    number, fy, seq = _next_receipt_number(student.branch, on)
    receipt = Receipt.objects.create(
        branch=student.branch, number=number, financial_year=fy, sequence=seq, student=student, date=on,
        mode=mode, reference=reference, amount=total, received_by=received_by, note=note,
    )
    ReceiptLine.objects.bulk_create(
        [ReceiptLine(receipt=receipt, charge_id=line.charge.pk, amount=money(line.amount)) for line in lines]
    )
    record("fees.collected", actor=received_by, detail={"receipt": number, "student": student.pk, "amount": str(total), "mode": mode})
    return receipt


@transaction.atomic
def cancel_receipt(*, receipt: Receipt, by: str, reason: str) -> Receipt:
    """The receipt keeps its number (no gaps) and stays on record; its lines
    stop counting as paid, so the dues reappear."""
    receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.cancelled_at:
        raise Conflict("Receipt is already cancelled.")
    if not reason.strip():
        raise Conflict("A reason is required to cancel a receipt.")
    receipt.cancelled_at = timezone.now()
    receipt.cancelled_by = by
    receipt.cancel_reason = reason.strip()
    receipt.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
    record("fees.receipt_cancelled", actor=by, detail={"receipt": receipt.number, "reason": receipt.cancel_reason})
    return receipt


@transaction.atomic
def refund(
    *, student, lines: list[LineIn], mode: str, reason: str, by: str, reference: str = "", on: date | None = None
) -> Refund:
    list(Charge.objects.select_for_update().filter(student=student, cancelled_at__isnull=True).values_list("pk"))
    balances = {c.pk: c for c in charges_with_balance(Charge.objects.filter(student=student))}
    total = ZERO
    for line in lines:
        bal = balances.get(line.charge.pk)
        if bal is None:
            raise Conflict("A selected charge is not a live charge of this student.")
        amt = money(line.amount)
        if amt <= 0 or amt > bal.paid:
            raise Conflict(f"Refund on “{bal.description}” must be between ₹0.01 and the ₹{bal.paid} paid.")
        total += amt
    if total <= 0:
        raise Conflict("Nothing to refund.")
    obj = Refund.objects.create(
        branch=student.branch, student=student, date=on or timezone.localdate(), mode=mode,
        reference=reference, amount=total, reason=reason, created_by=by,
    )
    RefundLine.objects.bulk_create([RefundLine(refund=obj, charge_id=l.charge.pk, amount=money(l.amount)) for l in lines])
    record("fees.refunded", actor=by, detail={"refund": obj.pk, "student": student.pk, "amount": str(total)})
    return obj


# ------------------------------------------------------------------ late fines
@transaction.atomic
def apply_late_fines(*, branch, as_of: date | None = None) -> int:
    """Create or grow the late fine on every overdue, unpaid charge whose head
    has a late-fine rule. Run daily (Celery beat) and before day-end reports.
    Returns the number of fine charges created or changed."""
    as_of = as_of or timezone.localdate()
    changed = 0
    overdue = charges_with_balance(
        Charge.objects.filter(branch=branch, parent__isnull=True)
        .exclude(head__late_fine_mode=FeeHead.LateFine.NONE)
        .exclude(source_type=Charge.Source.LATE_FINE)
        .select_related("head", "student", "student__branch")
    ).filter(outstanding__gt=0)
    late_head = head_for_kind(branch, FeeHead.Kind.LATE_FINE)
    for charge in overdue:
        head = charge.head
        days_late = (as_of - charge.due_date).days - head.grace_days
        if days_late <= 0:
            continue
        amount = money(head.late_fine_amount * days_late) if head.late_fine_mode == FeeHead.LateFine.PER_DAY else money(head.late_fine_amount)
        if amount <= 0:
            continue
        existing = Charge.objects.filter(
            source_type=Charge.Source.LATE_FINE, source_id=f"charge:{charge.pk}", cancelled_at__isnull=True
        ).first()
        if existing is None:
            post_charge(
                student=charge.student, head=late_head, amount=amount, due_date=as_of,
                description=f"Late fine — {charge.description}", source_type=Charge.Source.LATE_FINE,
                source_id=f"charge:{charge.pk}", academic_year=charge.academic_year, parent=charge,
            )
            changed += 1
        elif amount > existing.amount:
            Charge.objects.filter(pk=existing.pk).update(amount=amount)
            changed += 1
    return changed

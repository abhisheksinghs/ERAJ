"""Gate: visitors and outpasses (ADR-007). Parents are alerted at every
outpass step through apps.core.notify (log-only until the M7 adapters)."""
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from apps.core import notify
from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.hostel import mess as mess_services
from apps.hostel.models import ApprovedVisitor, MessLeave, MessMember, Outpass, Visit


# ------------------------------------------------------------------ visitors
@transaction.atomic
def visitor_arrives(*, student, name: str, relation: str = "", phone: str = "", id_proof: str = "",
                    purpose: str = "", visitor: ApprovedVisitor | None = None, by: str = "") -> Visit:
    """A visitor on the student's approved list goes in; anyone else is held
    until the warden approves."""
    if visitor is not None and visitor.student_id != student.pk:
        raise Conflict("That approved visitor belongs to another student.")
    if visitor is None and phone:
        visitor = ApprovedVisitor.objects.filter(student=student, phone=phone, deleted_at__isnull=True).first()
    if visitor is not None:
        name, relation, phone = visitor.name, relation or visitor.relation, phone or visitor.phone
    visit = Visit.objects.create(
        branch=student.branch, student=student, visitor=visitor, name=name, relation=relation, phone=phone,
        id_proof=id_proof, purpose=purpose,
        status=Visit.Status.IN if visitor else Visit.Status.HELD,
        time_in=timezone.now() if visitor else None,
    )
    record("hostel.visit", actor=by, detail={"visit": visit.pk, "student": student.pk, "status": visit.status})
    return visit


@transaction.atomic
def decide_visit(*, visit: Visit, approve: bool, by: str) -> Visit:
    if visit.status != Visit.Status.HELD:
        raise Conflict("This visitor is not waiting for approval.")
    visit.status = Visit.Status.IN if approve else Visit.Status.REFUSED
    visit.time_in = timezone.now() if approve else None
    visit.decided_by = by
    visit.save(update_fields=["status", "time_in", "decided_by", "updated_at"])
    return visit


@transaction.atomic
def visitor_leaves(*, visit: Visit) -> Visit:
    if visit.status != Visit.Status.IN:
        raise Conflict("This visitor is not inside.")
    visit.status = Visit.Status.OUT
    visit.time_out = timezone.now()
    visit.save(update_fields=["status", "time_out", "updated_at"])
    return visit


# ------------------------------------------------------------------ outpass
def _expected_back(op: Outpass) -> datetime:
    return timezone.make_aware(datetime.combine(op.to_date, op.return_by))


def _say(op: Outpass, event: str, text: str) -> None:
    notify.guardian(op.student, f"outpass.{event}", f"{op.student.full_name}: {text}")


@transaction.atomic
def request_outpass(*, student, from_date: date, to_date: date, reason: str, destination: str = "",
                    return_by=None, requested_by: str = Outpass.RequestedBy.WARDEN) -> Outpass:
    if to_date < from_date:
        raise Conflict("Return date is before the leaving date.")
    if Outpass.objects.filter(
        student=student, status__in=[Outpass.Status.REQUESTED, Outpass.Status.APPROVED, Outpass.Status.OUT],
        from_date__lte=to_date, to_date__gte=from_date,
    ).exists():
        raise Conflict("An outpass for these dates already exists.")
    op = Outpass.objects.create(
        branch=student.branch, student=student, from_date=from_date, to_date=to_date, reason=reason,
        destination=destination, requested_by=requested_by, **({"return_by": return_by} if return_by else {}),
    )
    _say(op, "requested", f"outpass requested {from_date:%d-%m-%Y} to {to_date:%d-%m-%Y}.")
    return op


@transaction.atomic
def decide_outpass(*, outpass: Outpass, approve: bool, by: str, note: str = "") -> Outpass:
    op = Outpass.objects.select_for_update().get(pk=outpass.pk)
    if op.status != Outpass.Status.REQUESTED:
        raise Conflict("Only a requested outpass can be approved or rejected.")
    op.status = Outpass.Status.APPROVED if approve else Outpass.Status.REJECTED
    op.decided_by, op.decision_note = by, note
    op.save(update_fields=["status", "decided_by", "decision_note", "updated_at"])
    if approve:
        member = MessMember.objects.filter(student=op.student, end_date__isnull=True).first()
        if member and not member.leaves.filter(from_date__lte=op.to_date, to_date__gte=op.from_date).exists():
            mess_services.record_leave(
                member=member, from_date=max(op.from_date, member.start_date), to_date=op.to_date,
                reason=f"Outpass: {op.reason}", outpass=op,
            )
    _say(op, "approved" if approve else "rejected",
         f"outpass {'approved' if approve else 'not approved'} by the warden{f' — {note}' if note else ''}.")
    return op


@transaction.atomic
def gate_out(*, outpass: Outpass) -> Outpass:
    op = Outpass.objects.select_for_update().get(pk=outpass.pk)
    if op.status != Outpass.Status.APPROVED:
        raise Conflict("Only an approved outpass can leave the gate.")
    op.status, op.checked_out_at = Outpass.Status.OUT, timezone.now()
    op.save(update_fields=["status", "checked_out_at", "updated_at"])
    _say(op, "out", f"left the hostel at {timezone.localtime(op.checked_out_at):%d-%m-%Y %H:%M}.")
    return op


@transaction.atomic
def gate_in(*, outpass: Outpass) -> Outpass:
    op = Outpass.objects.select_for_update().get(pk=outpass.pk)
    if op.status != Outpass.Status.OUT:
        raise Conflict("This student is not out on this outpass.")
    now = timezone.now()
    op.status, op.checked_in_at, op.is_late = Outpass.Status.RETURNED, now, now > _expected_back(op)
    op.save(update_fields=["status", "checked_in_at", "is_late", "updated_at"])
    back = timezone.localtime(now).date()
    leave = MessLeave.objects.filter(outpass=op).first()
    # Back before the planned date: leave ends on the return day (the return day
    # counts as leave, exactly as it does for an on-time return).
    if leave and back < leave.to_date:
        leave.to_date = max(back, leave.from_date)
        leave.save(update_fields=["to_date", "updated_at"])
    _say(op, "returned", f"returned at {timezone.localtime(now):%d-%m-%Y %H:%M}{' (late)' if op.is_late else ''}.")
    return op


@transaction.atomic
def cancel_outpass(*, outpass: Outpass) -> Outpass:
    if outpass.status not in (Outpass.Status.REQUESTED, Outpass.Status.APPROVED):
        raise Conflict("Only a requested or approved outpass can be cancelled.")
    outpass.status = Outpass.Status.CANCELLED
    outpass.save(update_fields=["status", "updated_at"])
    MessLeave.objects.filter(outpass=outpass).delete()
    _say(outpass, "cancelled", "outpass cancelled.")
    return outpass

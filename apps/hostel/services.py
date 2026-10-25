"""Hostel workflow (ADR-007). `allocate` / `vacate` take a row lock on the Room
so two concurrent allocations can't exceed capacity. Hostel fees and mess
enrolment happen in the same transaction (ADR-003: no signals for money)."""
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.core.licensing import tenant_has_module
from apps.hostel import mess as mess_services
from apps.hostel.dates import add_months, month_start, months_between
from apps.hostel.models import Allocation, HostelFeeRule, MaintenanceTicket, Mess, Room, Waitlist

FEE_DUE_DAY = 10


def fee_rule_for(room: Room) -> HostelFeeRule | None:
    rules = HostelFeeRule.objects.filter(branch=room.branch, is_active=True).filter(
        Q(block=room.block) | Q(block__isnull=True)
    ).filter(Q(room_type=room.room_type) | Q(room_type=""))
    # most specific first: block + type, block, type, branch-wide
    return min(rules, key=lambda r: (r.block_id is None, r.room_type == ""), default=None)


def _post_hostel_fees(alloc: Allocation) -> int:
    if not tenant_has_module("fees"):
        return 0
    rule = fee_rule_for(alloc.room)
    if rule is None:
        return 0
    from apps.fees import services as fees
    from apps.fees.models import Charge, FeeHead
    from apps.people.models import AcademicYear

    year = AcademicYear.objects.filter(start_date__lte=alloc.check_in_date, end_date__gte=alloc.check_in_date).first()
    last = month_start(year.end_date) if year else month_start(alloc.check_in_date)
    n = 0
    for m in months_between(month_start(alloc.check_in_date), last):
        fees.post_charge(
            student=alloc.student, amount=rule.monthly_amount, kind=FeeHead.Kind.HOSTEL, academic_year=year,
            due_date=max(m.replace(day=FEE_DUE_DAY), alloc.check_in_date),
            description=f"Hostel {alloc.room} — {m:%b %Y}",
            source_type=Charge.Source.HOSTEL, source_id=f"alloc:{alloc.pk}:{m:%Y-%m}",
        )
        n += 1
    return n


@transaction.atomic
def allocate(*, student, room: Room, on: date | None = None, mess_plan: str | None = None) -> Allocation:
    room = Room.objects.select_for_update().select_related("block").get(pk=room.pk)
    if student.branch_id != room.branch_id:
        raise Conflict("Student and room belong to different branches.")
    if room.status != Room.Status.ACTIVE:
        raise Conflict(f"Room {room} is {room.get_status_display().lower()}.")
    if room.maintenance_tickets.filter(status=MaintenanceTicket.Status.OPEN).exists():
        raise Conflict(f"Room {room} has an open repair ticket.")
    if room.allocations.filter(check_out_date__isnull=True).count() >= room.capacity:
        raise Conflict(f"Room {room} is full.")
    gender = room.gender if room.gender != Room.Gender.ANY else room.block.gender
    if gender != Room.Gender.ANY and student.gender and student.gender != gender:
        raise Conflict(f"Room {room} is for {Room.Gender(gender).label.lower()}.")
    if student.hostel_allocations.filter(check_out_date__isnull=True).exists():
        raise Conflict("This student already has a bed.")

    alloc = Allocation.objects.create(
        branch=room.branch, student=student, room=room, check_in_date=on or timezone.localdate()
    )
    Waitlist.objects.filter(
        student=student, room=room, status__in=[Waitlist.Status.WAITING, Waitlist.Status.OFFERED]
    ).update(status=Waitlist.Status.FULFILLED)
    _post_hostel_fees(alloc)

    mess = Mess.objects.filter(blocks=room.block, deleted_at__isnull=True).order_by("pk").first()
    if mess and not student.mess_memberships.filter(end_date__isnull=True).exists():
        mess_services.enrol(
            mess=mess, student=student, plan=mess_plan or "monthly", start=alloc.check_in_date, allocation=alloc
        )
    record("hostel.allocate", detail={"allocation": alloc.pk, "student": student.pk, "room": room.pk})
    return alloc


@transaction.atomic
def vacate(*, allocation: Allocation, on: date | None = None, reason: str = "") -> Allocation:
    allocation = Allocation.objects.select_for_update().get(pk=allocation.pk)
    if allocation.check_out_date:
        raise Conflict("This student has already vacated.")
    on = on or timezone.localdate()
    if on < allocation.check_in_date:
        raise Conflict("Vacate date is before the check-in date.")
    allocation.check_out_date = on
    allocation.vacate_reason = reason
    allocation.save(update_fields=["check_out_date", "vacate_reason", "updated_at"])

    if tenant_has_module("fees"):
        from apps.fees import services as fees
        from apps.fees.models import Charge

        fees.cancel_future_charges(
            student=allocation.student, source_type=Charge.Source.HOSTEL, source_prefix=f"alloc:{allocation.pk}:",
            from_date=add_months(month_start(on), 1), reason="Vacated hostel",
        )
    for member in allocation.mess_memberships.filter(end_date__isnull=True):
        mess_services.end_membership(member=member, on=on)

    offer = allocation.room.waitlist.filter(status=Waitlist.Status.WAITING).order_by("created_at").first()
    if offer:
        offer.status = Waitlist.Status.OFFERED
        offer.save(update_fields=["status", "updated_at"])

    record("hostel.vacate", detail={"allocation": allocation.pk, "on": str(on)})
    return allocation


@transaction.atomic
def add_to_waitlist(*, student, room: Room) -> Waitlist:
    if room.available_beds > 0 and room.status == Room.Status.ACTIVE and not room.has_open_maintenance:
        raise Conflict("This room has a free bed — allocate it directly.")
    if Waitlist.objects.filter(
        room=room, student=student, status__in=[Waitlist.Status.WAITING, Waitlist.Status.OFFERED]
    ).exists():
        raise Conflict("This student is already waiting for this room.")
    return Waitlist.objects.create(branch=room.branch, room=room, student=student)


@transaction.atomic
def open_ticket(*, room: Room, summary: str, details: str = "") -> MaintenanceTicket:
    return MaintenanceTicket.objects.create(branch=room.branch, room=room, summary=summary, details=details)


@transaction.atomic
def close_ticket(*, ticket: MaintenanceTicket, action_taken: str = "") -> MaintenanceTicket:
    if ticket.status == MaintenanceTicket.Status.CLOSED:
        raise Conflict("Ticket already closed.")
    ticket.status = MaintenanceTicket.Status.CLOSED
    ticket.action_taken = action_taken
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=["status", "action_taken", "closed_at", "updated_at"])
    record("hostel.ticket_closed", detail={"ticket": ticket.pk, "room": ticket.room_id})
    return ticket

"""Allocation workflow. `allocate` / `vacate` take a row lock on the Room so
two concurrent allocations can't exceed capacity.

`allocation_changed` is fired for a future Fees module to hook — no receiver
yet. ponytail: bare signal, wire Fees in when it exists.
"""
from django.db import transaction
from django.dispatch import Signal
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.hostel.models import Allocation, MaintenanceTicket, Room, Waitlist

allocation_changed = Signal()  # kwargs: allocation, action ("allocated" | "vacated")


@transaction.atomic
def allocate(*, resident, room: Room) -> Allocation:
    room = Room.objects.select_for_update().get(pk=room.pk)
    if room.status != Room.Status.ACTIVE:
        raise Conflict(f"Room is {room.get_status_display().lower()}.")
    if room.maintenance_tickets.filter(status=MaintenanceTicket.Status.OPEN).exists():
        raise Conflict("Room has an open maintenance ticket.")
    active = room.allocations.filter(check_out_date__isnull=True).count()
    if active >= room.capacity:
        raise Conflict("Room is at capacity.")
    if resident.allocations.filter(check_out_date__isnull=True).exists():
        raise Conflict("Resident already has an active allocation.")

    alloc = Allocation.objects.create(resident=resident, room=room)
    record("hostel.allocate", detail={"allocation": alloc.pk, "resident": resident.pk, "room": room.pk})
    allocation_changed.send(sender=allocate, allocation=alloc, action="allocated")
    return alloc


@transaction.atomic
def vacate(*, allocation: Allocation) -> Allocation:
    if allocation.check_out_date:
        raise Conflict("Allocation is already closed.")
    allocation.check_out_date = timezone.localdate()
    allocation.save(update_fields=["check_out_date", "updated_at"])

    offer = (
        allocation.room.waitlist.filter(status=Waitlist.Status.WAITING)
        .order_by("created_at")
        .first()
    )
    if offer:
        offer.status = Waitlist.Status.OFFERED
        offer.save(update_fields=["status", "updated_at"])

    record("hostel.vacate", detail={"allocation": allocation.pk})
    allocation_changed.send(sender=vacate, allocation=allocation, action="vacated")
    return allocation


@transaction.atomic
def close_ticket(*, ticket: MaintenanceTicket) -> MaintenanceTicket:
    if ticket.status == MaintenanceTicket.Status.CLOSED:
        raise Conflict("Ticket already closed.")
    ticket.status = MaintenanceTicket.Status.CLOSED
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=["status", "closed_at", "updated_at"])
    record("hostel.ticket_closed", detail={"ticket": ticket.pk, "room": ticket.room_id})
    return ticket

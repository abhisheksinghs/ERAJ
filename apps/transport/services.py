from django.db import transaction
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.transport.models import TransportAssignment, Vehicle


@transaction.atomic
def assign(*, vehicle: Vehicle, rider_name: str, rider_contact: str = "", pickup_point: str = ""):
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if vehicle.active_riders >= vehicle.capacity:
        raise Conflict("Vehicle is at capacity.")
    assignment = TransportAssignment.objects.create(
        vehicle=vehicle, rider_name=rider_name, rider_contact=rider_contact, pickup_point=pickup_point
    )
    record("transport.assigned", detail={"assignment": assignment.pk, "vehicle": vehicle.pk})
    return assignment


@transaction.atomic
def unassign(*, assignment: TransportAssignment):
    if assignment.removed_at:
        raise Conflict("Already removed.")
    assignment.removed_at = timezone.now()
    assignment.save(update_fields=["removed_at", "updated_at"])
    record("transport.unassigned", detail={"assignment": assignment.pk})
    return assignment

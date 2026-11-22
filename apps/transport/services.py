"""Transport rules (ADR-010): fares, capacity, monthly charges, GPS positions and alerts."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.core.licensing import tenant_has_module
from apps.transport.models import (
    FareSlab, Route, RouteStop, TransportAlert, TransportAssignment, TransportSettings, Vehicle, VehicleDocument,
    VehiclePosition,
)

FEE_DUE_DAY = 10


def settings_for(branch) -> TransportSettings:
    obj, _ = TransportSettings.objects.get_or_create(branch=branch)
    return obj


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


# ------------------------------------------------------------------ fares
def fare_for(stop: RouteStop) -> Decimal:
    if stop.monthly_fare is not None:
        return stop.monthly_fare
    if stop.distance_km is not None:
        slab = FareSlab.objects.filter(branch=stop.branch, from_km__lte=stop.distance_km, to_km__gte=stop.distance_km).order_by("from_km").first()
        if slab:
            return slab.monthly_fare
    raise Conflict(f"No fare for stop {stop.name}: set its monthly fare, or its distance and a fare slab.")


# ------------------------------------------------------------------ capacity
def riders_overlapping(vehicle: Vehicle, start: date, exclude=None):
    qs = TransportAssignment.objects.filter(vehicle=vehicle).filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


def occupancy(vehicle: Vehicle, on: date | None = None) -> int:
    on = on or timezone.localdate()
    return TransportAssignment.objects.filter(vehicle=vehicle, start_date__lte=on).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=on)).count()


# ------------------------------------------------------------------ fees
def _post_fees(a: TransportAssignment) -> int:
    if a.student_id is None or not tenant_has_module("fees") or not a.monthly_fare:
        return 0
    from apps.fees import services as fees
    from apps.fees.models import Charge, FeeHead
    from apps.people.models import AcademicYear

    year = AcademicYear.objects.filter(start_date__lte=a.start_date, end_date__gte=a.start_date).first()
    last = month_start(a.end_date) if a.end_date else (month_start(year.end_date) if year else month_start(a.start_date))
    n, m = 0, month_start(a.start_date)
    while m <= last:
        fees.post_charge(
            student=a.student, amount=a.monthly_fare, kind=FeeHead.Kind.TRANSPORT, academic_year=year,
            due_date=max(m.replace(day=FEE_DUE_DAY), a.start_date),
            description=f"Transport {a.route.code} — {a.stop.name} — {m:%b %Y}",
            source_type=Charge.Source.TRANSPORT, source_id=f"assign:{a.pk}:{m:%Y-%m}",
        )
        n += 1
        m = add_months(m, 1)
    return n


def _cancel_fees(a: TransportAssignment, from_month: date, reason: str) -> int:
    if a.student_id is None or not tenant_has_module("fees"):
        return 0
    from apps.fees import services as fees
    from apps.fees.models import Charge

    return fees.cancel_future_charges(student=a.student, source_type=Charge.Source.TRANSPORT,
                                      source_prefix=f"assign:{a.pk}:", from_date=from_month, reason=reason)


# ------------------------------------------------------------------ assignment
def _rider_label(student, staff) -> str:
    return (student or staff).full_name


@transaction.atomic
def assign(*, stop: RouteStop, vehicle: Vehicle, start: date, student=None, staff=None, note: str = "", by: str = "") -> TransportAssignment:
    if (student is None) == (staff is None):
        raise Conflict("Choose a student or a staff member.")
    rider = student or staff
    if rider.status != "active":
        raise Conflict(f"{rider.full_name} is not active.")
    if vehicle.branch_id != rider.branch_id or stop.branch_id != rider.branch_id:
        raise Conflict("Rider, stop and vehicle must belong to the same branch.")
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if not vehicle.is_active:
        raise Conflict(f"{vehicle} is not in service.")
    if vehicle.route_id != stop.route_id:
        raise Conflict(f"{vehicle} doesn't run on route {stop.route.code}.")
    who = {"student": student} if student else {"staff": staff}
    clash = TransportAssignment.objects.filter(**who).filter(Q(end_date__isnull=True) | Q(end_date__gte=start)).first()
    if clash:
        raise Conflict(f"{rider.full_name} already rides {clash.vehicle} from {clash.stop.name}; change or stop that first.")
    taken = riders_overlapping(vehicle, start).count()
    if taken >= vehicle.capacity:
        raise Conflict(f"{vehicle} is full ({taken} of {vehicle.capacity} seats).")
    fare = fare_for(stop) if student else Decimal("0")
    a = TransportAssignment.objects.create(branch=vehicle.branch, route=stop.route, stop=stop, vehicle=vehicle,
                                           start_date=start, monthly_fare=fare, note=note, **who)
    months = _post_fees(a)
    record("transport.assigned", actor=by or "system", assignment=a.pk, rider=_rider_label(student, staff),
           vehicle=vehicle.registration_no, stop=stop.name, fare=str(fare), months=months)
    return a


def _first_unbilled_month(from_date: date) -> date:
    """Stopping on the 1st stops that month's fee; mid-month, the month is charged."""
    return month_start(from_date) if from_date.day == 1 else add_months(from_date, 1)


@transaction.atomic
def stop(*, assignment: TransportAssignment, from_date: date, by: str = "", reason: str = "Transport stopped") -> TransportAssignment:
    a = TransportAssignment.objects.select_for_update().get(pk=assignment.pk)
    if a.end_date is not None and a.end_date < from_date:
        raise Conflict("Transport has already stopped for this rider.")
    if from_date <= a.start_date:
        # never rode: cancel the whole assignment
        a.end_date = a.start_date
        cancelled = _cancel_fees(a, month_start(a.start_date), reason)
        a.delete()
        record("transport.assignment_withdrawn", actor=by or "system", assignment=assignment.pk, charges_cancelled=cancelled)
        assignment.end_date = assignment.start_date
        return assignment
    a.end_date = from_date - timedelta(days=1)
    a.save(update_fields=["end_date", "updated_at"])
    cancelled = _cancel_fees(a, _first_unbilled_month(from_date), reason)
    record("transport.stopped", actor=by or "system", assignment=a.pk, from_date=str(from_date), charges_cancelled=cancelled)
    return a


@transaction.atomic
def change(*, assignment: TransportAssignment, stop_to: RouteStop, vehicle: Vehicle, from_date: date, by: str = "") -> TransportAssignment:
    a = TransportAssignment.objects.select_related("student", "staff").get(pk=assignment.pk)
    student, staff = a.student, a.staff
    if from_date <= a.start_date:
        raise Conflict("A change starts after the current assignment began; to correct it, stop it and assign again.")
    stop(assignment=a, from_date=from_date, by=by, reason="Changed stop/vehicle")
    return assign(stop=stop_to, vehicle=vehicle, start=from_date, student=student, staff=staff, by=by,
                  note=f"Changed from {a.stop.name} / {a.vehicle}")


# ------------------------------------------------------------------ GPS
def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp, dl = p2 - p1, math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _alert(*, vehicle, kind, key, at, detail, stop=None) -> TransportAlert | None:
    try:
        with transaction.atomic():
            return TransportAlert.objects.create(branch=vehicle.branch, vehicle=vehicle, kind=kind, key=key, at=at,
                                                 detail=detail, stop=stop)
    except IntegrityError:
        return None  # already raised for this vehicle/stop/session


def riders_at(stop: RouteStop, vehicle: Vehicle, on: date):
    return (TransportAssignment.objects.filter(stop=stop, vehicle=vehicle, student__isnull=False, start_date__lte=on)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=on)).select_related("student"))


@transaction.atomic
def ingest_position(*, vehicle: Vehicle, lat, lng, at: datetime, speed=0) -> dict:
    """Store one position; raise over-speed and "bus near your stop" alerts."""
    from apps.core import notify

    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    lat, lng, speed = Decimal(str(lat)).quantize(Decimal("0.000001")), Decimal(str(lng)).quantize(Decimal("0.000001")), Decimal(str(speed or 0))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or speed < 0 or speed > 250:
        raise Conflict("Position out of range.")
    try:
        with transaction.atomic():
            VehiclePosition.objects.create(vehicle=vehicle, recorded_at=at, latitude=lat, longitude=lng, speed_kmph=speed)
    except IntegrityError:
        return {"stored": False, "alerts": 0}
    v = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if v.last_seen_at is None or at >= v.last_seen_at:
        v.last_latitude, v.last_longitude, v.last_speed_kmph, v.last_seen_at = lat, lng, speed, at
        v.save(update_fields=["last_latitude", "last_longitude", "last_speed_kmph", "last_seen_at", "updated_at"])
    cfg = settings_for(v.branch)
    local = timezone.localtime(at)
    alerts = 0
    if speed > cfg.speed_limit_kmph:
        bucket = local.strftime("%Y%m%d%H") + str(local.minute // 10)
        if _alert(vehicle=v, kind=TransportAlert.Kind.OVER_SPEED, key=f"speed:{v.pk}:{bucket}", at=at,
                  detail=f"{v} at {speed} km/h (limit {cfg.speed_limit_kmph})"):
            notify.staff_role(v.branch, "transport", "transport.over_speed",
                              f"{v} was driving at {speed} km/h at {local:%H:%M} (limit {cfg.speed_limit_kmph} km/h).")
            alerts += 1
    if v.route_id:
        session = "am" if local.hour < 12 else "pm"
        for s in RouteStop.objects.filter(route_id=v.route_id, latitude__isnull=False, longitude__isnull=False):
            if haversine_m(lat, lng, s.latitude, s.longitude) > cfg.near_stop_meters:
                continue
            al = _alert(vehicle=v, kind=TransportAlert.Kind.NEAR_STOP, key=f"near:{v.pk}:{s.pk}:{local:%Y%m%d}:{session}",
                        at=at, detail=f"{v} near {s.name}", stop=s)
            if al is None:
                continue
            n = 0
            for a in riders_at(s, v, local.date()):
                notify.guardian(a.student, "transport.near_stop",
                                f"Bus {v} is about {cfg.near_stop_meters} m from {s.name} ({local:%H:%M}).")
                n += 1
            al.recipients = n
            al.save(update_fields=["recipients", "updated_at"])
            alerts += 1
    return {"stored": True, "alerts": alerts}


def live(branch) -> list[dict]:
    now = timezone.now()
    out = []
    for v in Vehicle.objects.filter(branch=branch, is_active=True).select_related("route"):
        age = int((now - v.last_seen_at).total_seconds()) if v.last_seen_at else None
        out.append({"vehicle": v.pk, "registration_no": v.registration_no, "route": v.route.code if v.route else "",
                    "route_name": v.route.name if v.route else "", "driver": v.driver_name, "driver_phone": v.driver_phone,
                    "lat": v.last_latitude, "lng": v.last_longitude, "speed": v.last_speed_kmph,
                    "seen_at": v.last_seen_at, "age_seconds": age, "riders": occupancy(v), "capacity": v.capacity})
    return out


def trip(vehicle: Vehicle, on: date) -> list[dict]:
    start = timezone.make_aware(datetime.combine(on, datetime.min.time()))
    return [{"at": p.recorded_at, "lat": p.latitude, "lng": p.longitude, "speed": p.speed_kmph}
            for p in VehiclePosition.objects.filter(vehicle=vehicle, recorded_at__gte=start, recorded_at__lt=start + timedelta(days=1))]


# ------------------------------------------------------------------ reports
def riders(*, branch, route: Route | None = None, on: date | None = None) -> list[dict]:
    on = on or timezone.localdate()
    qs = (TransportAssignment.objects.filter(branch=branch, start_date__lte=on).filter(Q(end_date__isnull=True) | Q(end_date__gte=on))
          .select_related("route", "stop", "vehicle", "student", "staff")
          .prefetch_related("student__guardian_links__guardian", "student__enrollments__program", "student__enrollments__section"))
    if route is not None:
        qs = qs.filter(route=route)
    rows = []
    for a in qs.order_by("route__code", "stop__sequence", "student__full_name", "staff__full_name"):
        phone, klass = "", ""
        if a.student_id:
            links = list(a.student.guardian_links.all())
            link = next((g for g in links if g.is_primary), links[0] if links else None)
            phone = link.guardian.phone if link else a.student.phone
            enr = a.student.current_enrollment
            klass = f"{enr.program}-{enr.section.name}" if enr and enr.section else (str(enr.program) if enr else "")
        rows.append({"route": a.route.code, "route_name": a.route.name, "stop_no": a.stop.sequence, "stop": a.stop.name,
                     "pickup": a.stop.pickup_time, "drop": a.stop.drop_time, "vehicle": a.vehicle.registration_no,
                     "rider": a.rider.full_name, "type": "student" if a.student_id else "staff",
                     "id_no": a.student.admission_no if a.student_id else a.staff.employee_code, "class": klass,
                     "guardian_phone": phone if a.student_id else a.staff.phone, "monthly_fare": a.monthly_fare})
    return rows


def occupancy_report(*, branch) -> list[dict]:
    out = []
    for v in Vehicle.objects.filter(branch=branch, is_active=True).select_related("route"):
        n = occupancy(v)
        out.append({"vehicle": v.registration_no, "route": v.route.code if v.route else "", "capacity": v.capacity,
                    "riders": n, "free": max(v.capacity - n, 0), "percent": round(100 * n / v.capacity) if v.capacity else 0})
    return out


def expiring_documents(*, branch, within_days: int = 30, on: date | None = None) -> list[dict]:
    on = on or timezone.localdate()
    rows = []
    for d in (VehicleDocument.objects.filter(vehicle__branch=branch, expires_on__lte=on + timedelta(days=within_days))
              .select_related("vehicle").order_by("expires_on")):
        rows.append({"id": d.pk, "vehicle": d.vehicle.registration_no, "document": d.get_kind_display(), "number": d.number,
                     "expires_on": d.expires_on, "days_left": (d.expires_on - on).days, "expired": d.expires_on < on})
    return rows


def remind_expiring(*, branch, on: date | None = None) -> int:
    """Daily: one alert per document at the reminder threshold, expiry day and after."""
    from apps.core import notify

    on = on or timezone.localdate()
    days = settings_for(branch).document_remind_days
    n = 0
    for row in expiring_documents(branch=branch, within_days=days, on=on):
        doc = VehicleDocument.objects.select_related("vehicle").get(pk=row["id"])
        key = f"doc:{doc.pk}:{doc.expires_on:%Y%m%d}:{'expired' if row['expired'] else 'due'}"
        if _alert(vehicle=doc.vehicle, kind=TransportAlert.Kind.DOCUMENT, key=key, at=timezone.now(),
                  detail=f"{row['document']} of {row['vehicle']} {'expired' if row['expired'] else 'expires'} on {doc.expires_on:%d-%m-%Y}"):
            notify.staff_role(branch, "transport", "transport.document_expiring",
                              f"{row['document']} of {row['vehicle']} {'expired' if row['expired'] else 'expires'} on {doc.expires_on:%d-%m-%Y}.")
            n += 1
    return n

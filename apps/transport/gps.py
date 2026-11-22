"""GPS sources (ADR-005, ADR-010).

1. Push — POST /api/transport/gps/push/ with header X-Device-Key (the vehicle's key). Any tracker or
   provider that can call a URL: {"lat": 25.6, "lng": 85.1, "speed": 32, "time": "2026-11-22 07:41:05"}
   or {"positions": [ … ]}. Time is local (India) or ISO 8601 with offset; omitted = now.
2. Simulated — `python manage.py simulate_gps` drives vehicles along their route stops (staging).
A provider that only offers a pull API gets a poller adapter here once named (scope open question).
"""
from __future__ import annotations

import json
from datetime import datetime

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.core.exceptions import Conflict
from apps.transport import services
from apps.transport.models import Vehicle

FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S")


def _parse_time(value) -> datetime:
    if value in (None, ""):
        return timezone.now()
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in FORMATS:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unrecognised time: {text!r}")
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def _client_ip(request) -> str | None:
    from apps.attendance.devices import _client_ip as ip  # same proxy handling as attendance devices

    return ip(request)


def _tenant_ok() -> bool:
    from apps.core.licensing import tenant_has_module

    return getattr(connection, "schema_name", "public") != "public" and tenant_has_module("transport")


@csrf_exempt
def push(request):
    if request.method != "POST":
        return JsonResponse({"detail": "POST only."}, status=405)
    if not _tenant_ok():
        return JsonResponse({"detail": "Transport is not part of this institution's plan."}, status=402)
    key = request.headers.get("X-Device-Key", "")
    vehicle = Vehicle.objects.filter(gps_key=key, is_active=True).first() if key else None
    if vehicle is None or not vehicle.ip_allowed(_client_ip(request)):
        return JsonResponse({"detail": "Unknown device key."}, status=403)
    try:
        payload = json.loads(request.body or b"{}")
        items = payload.get("positions", [payload]) if isinstance(payload, dict) else payload
        if len(items) > 1000:
            return JsonResponse({"detail": "At most 1000 positions per call."}, status=400)
        parsed = [(p["lat"], p["lng"], _parse_time(p.get("time")), p.get("speed", 0)) for p in items]
    except (ValueError, KeyError, TypeError) as exc:
        return JsonResponse({"detail": f"Bad payload: {exc}"}, status=400)
    stored = alerts = 0
    try:
        for lat, lng, at, speed in sorted(parsed, key=lambda x: x[2]):
            r = services.ingest_position(vehicle=vehicle, lat=lat, lng=lng, at=at, speed=speed)
            stored += r["stored"]
            alerts += r["alerts"]
    except Conflict as exc:
        return JsonResponse({"detail": str(exc.detail)}, status=400)
    return JsonResponse({"stored": stored, "alerts": alerts})


def simulate_step(vehicle: Vehicle, fraction: float, *, at=None, speed=30) -> None:
    """Place a vehicle `fraction` (0–1) of the way along its route's stops (staging only)."""
    stops = [s for s in vehicle.route.stops.order_by("sequence") if s.latitude is not None] if vehicle.route else []
    if len(stops) < 2:
        return
    pos = fraction * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    t = pos - i
    a, b = stops[i], stops[i + 1]
    lat = float(a.latitude) + (float(b.latitude) - float(a.latitude)) * t
    lng = float(a.longitude) + (float(b.longitude) - float(a.longitude)) * t
    services.ingest_position(vehicle=vehicle, lat=lat, lng=lng, at=at or timezone.now(), speed=speed)

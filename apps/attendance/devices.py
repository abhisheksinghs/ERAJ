"""Attendance device adapters (ADR-005, ADR-008).

Three ways punches arrive:
  1. ADMS push — the cloud protocol of ZKTeco devices, also spoken by eSSL,
     Realtime and Identix. The device calls  /iclock/cdata  and  /iclock/getrequest
     on the institution's own address, identified by its serial number.
  2. JSON push — POST /api/attendance/push/ with header X-Device-Key, for any
     other device or vendor software that can call a URL.
  3. File import — any device's punch log exported to Excel/CSV.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time

from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.attendance import services
from apps.attendance.models import AttendanceDevice, Punch

log = logging.getLogger("eraj.attendance.devices")

DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M", "%Y/%m/%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
)
CODE_HEADERS = ("code", "card", "card no", "card_no", "cardno", "user id", "userid", "user_id", "emp code",
                "employee code", "empcode", "enroll no", "enrollno", "enroll_no", "pin", "badge", "id")
DATETIME_HEADERS = ("time", "datetime", "date time", "date_time", "punch time", "punch_time", "log time",
                    "logtime", "checktime", "check time", "timestamp")


class PunchParseError(ValueError):
    pass


def parse_datetime(value, *, time_value=None) -> datetime:
    """A device time (local, India) → aware datetime."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date) and time_value is not None:
        t = time_value if isinstance(time_value, time) else parse_datetime(f"2000-01-01 {str(time_value).strip()}").time()
        dt = datetime.combine(value, t)
    else:
        text = str(value).strip()
        if time_value not in (None, ""):
            tv = time_value.strftime("%H:%M:%S") if isinstance(time_value, time) else str(time_value).strip()
            text = f"{text} {tv}"
        for fmt in DATETIME_FORMATS:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise PunchParseError(f"Unrecognised date/time: {text!r}")
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def parse_adms_attlog(body: str) -> list[tuple[str, datetime]]:
    """ATTLOG lines: PIN<TAB>YYYY-MM-DD HH:MM:SS<TAB>status<TAB>verify…"""
    out = []
    for line in body.splitlines():
        parts = line.strip().split("\t")
        if len(parts) >= 2 and parts[0]:
            try:
                out.append((parts[0].strip(), parse_datetime(parts[1])))
            except PunchParseError:
                log.warning("adms: bad line %r", line)
    return out


def rows_to_punches(rows: list[dict]) -> tuple[list[tuple[str, datetime]], list[dict]]:
    """Header-detected Excel/CSV rows → punches + row errors (row numbers as in the file)."""
    if not rows:
        return [], []
    keys = list(rows[0].keys())
    code_key = next((k for k in CODE_HEADERS if k in keys), None)
    dt_key = next((k for k in DATETIME_HEADERS if k in keys), None)
    date_key = "date" if "date" in keys else None
    if code_key is None or (dt_key is None and date_key is None):
        raise PunchParseError(
            "Could not find the columns. The file needs a card/user code column (e.g. 'User ID', 'Card No') "
            "and a 'Time' column, or 'Date' and 'Time' columns."
        )
    punches, errors = [], []
    for i, row in enumerate(rows, start=2):
        code = row.get(code_key)
        if isinstance(code, float) and code.is_integer():
            code = int(code)
        code = str(code or "").strip()
        try:
            if not code:
                raise PunchParseError("No card / user code.")
            if date_key and dt_key and dt_key != date_key and not isinstance(row.get(dt_key), datetime):
                at = parse_datetime(row[date_key], time_value=row.get(dt_key))
            else:
                at = parse_datetime(row[dt_key or date_key])
            punches.append((code, at))
        except (PunchParseError, KeyError) as exc:
            errors.append({"row": i, "errors": [str(exc)]})
    return punches, errors


def ingest(*, device: AttendanceDevice | None, branch, punches, source: str) -> dict:
    stored = duplicates = unknown = 0
    for code, at in punches:
        p = services.ingest_punch(branch=branch, code=code, at=at, device=device, source=source)
        if p is None:
            duplicates += 1
        else:
            stored += 1
            unknown += p.student_id is None and p.staff_id is None
    if device is not None:
        AttendanceDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
    return {"received": len(punches), "stored": stored, "duplicates": duplicates, "unknown_codes": unknown}


def _client_ip(request) -> str | None:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")


def _tenant_ok() -> bool:
    from apps.core.licensing import tenant_has_module

    return tenant_has_module("attendance")


def _adms_device(request) -> AttendanceDevice | None:
    sn = request.GET.get("SN", "").strip()
    device = AttendanceDevice.objects.filter(serial_no=sn, is_active=True, brand__in=AttendanceDevice.ADMS_BRANDS).first()
    if device is None or not device.ip_allowed(_client_ip(request)):
        log.warning("adms: refused SN=%r from %s (schema %s)", sn, _client_ip(request), connection.schema_name)
        return None
    return device


@csrf_exempt
def adms_cdata(request):
    """ZKTeco ADMS: GET = handshake (send options), POST = upload (ATTLOG…)."""
    if not _tenant_ok():
        return HttpResponse("ERROR: module not licensed", status=403, content_type="text/plain")
    device = _adms_device(request)
    if device is None:
        return HttpResponse("ERROR: unknown device", status=403, content_type="text/plain")
    if request.method == "GET":
        AttendanceDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
        options = "\n".join([
            f"GET OPTION FROM: {device.serial_no}", "ATTLOGStamp=None", "OPERLOGStamp=9999", "ATTPHOTOStamp=None",
            "ErrorDelay=30", "Delay=10", "TransTimes=00:00;14:05", "TransInterval=1", "TransFlag=TransData AttLog",
            "Realtime=1", "Encrypt=None",
        ])
        return HttpResponse(options + "\n", content_type="text/plain")
    if request.GET.get("table", "").upper() != "ATTLOG":
        return HttpResponse("OK", content_type="text/plain")  # OPERLOG, ATTPHOTO… not used
    punches = parse_adms_attlog(request.body.decode("utf-8", "replace"))
    result = ingest(device=device, branch=device.branch, punches=punches, source=Punch.Source.PUSH)
    return HttpResponse(f"OK: {result['received']}", content_type="text/plain")


@csrf_exempt
def adms_getrequest(request):
    """ADMS command poll: we never send commands to devices."""
    if not _tenant_ok() or _adms_device(request) is None:
        return HttpResponse("ERROR", status=403, content_type="text/plain")
    AttendanceDevice.objects.filter(serial_no=request.GET.get("SN", "")).update(last_seen_at=timezone.now())
    return HttpResponse("OK", content_type="text/plain")


@csrf_exempt
def json_push(request):
    """POST {"punches": [{"code": "1001", "time": "2026-10-25 08:01:12"}, …]} with X-Device-Key."""
    if request.method != "POST":
        return JsonResponse({"detail": "POST only."}, status=405)
    if not _tenant_ok():
        return JsonResponse({"detail": "Attendance is not part of this institution's plan."}, status=402)
    key = request.headers.get("X-Device-Key", "")
    device = AttendanceDevice.objects.filter(token=key, is_active=True).first() if key else None
    if device is None or not device.ip_allowed(_client_ip(request)):
        return JsonResponse({"detail": "Unknown device key."}, status=403)
    try:
        payload = json.loads(request.body or b"{}")
        items = payload.get("punches", []) if isinstance(payload, dict) else payload
        punches = [(str(p["code"]), parse_datetime(p["time"])) for p in items]
    except (ValueError, KeyError, TypeError, PunchParseError) as exc:
        return JsonResponse({"detail": f"Bad payload: {exc}"}, status=400)
    if len(punches) > 5000:
        return JsonResponse({"detail": "At most 5000 punches per call."}, status=400)
    return JsonResponse(ingest(device=device, branch=device.branch, punches=punches, source=Punch.Source.PUSH))

from django.db import transaction
from django.db.models import Count

from apps.attendance.models import AttendanceRecord
from apps.core.audit import record

# Late and half-day count as attended for the percentage; half-day counts half.
_WEIGHT = {"present": 1.0, "late": 1.0, "half_day": 0.5}


@transaction.atomic
def mark(*, student, date, status, period=None, subject=None, marked_by=""):
    """Idempotent: marking the same student/date/period again updates the
    status instead of raising on the unique constraint."""
    rec, _ = AttendanceRecord.objects.update_or_create(
        student=student,
        date=date,
        period=period,
        defaults={"status": status, "subject": subject, "marked_by": marked_by, "branch": student.branch},
    )
    record(
        "attendance.marked",
        actor=marked_by,
        detail={"student": student.pk, "date": str(date), "period": period, "status": status},
    )
    return rec


def summary(*, student, date_from=None, date_to=None) -> dict:
    qs = AttendanceRecord.objects.filter(student=student)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    by_status = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
    total = sum(by_status.values())
    attended = sum(_WEIGHT.get(s, 0.0) * n for s, n in by_status.items())
    return {
        "present": by_status.get("present", 0),
        "absent": by_status.get("absent", 0),
        "leave": by_status.get("leave", 0),
        "late": by_status.get("late", 0),
        "half_day": by_status.get("half_day", 0),
        "total": total,
        "percentage": round(attended / total * 100, 1) if total else 0.0,
    }

from django.db import transaction
from django.db.models import Count

from apps.attendance.models import AttendanceRecord
from apps.core.audit import record


@transaction.atomic
def mark(*, student, date, status, marked_by=""):
    """Idempotent: marking the same student/date again updates the status
    instead of raising on the unique constraint."""
    rec, _ = AttendanceRecord.objects.update_or_create(
        student=student, date=date, defaults={"status": status, "marked_by": marked_by}
    )
    record(
        "attendance.marked",
        actor=marked_by,
        detail={"student": student.pk, "date": str(date), "status": status},
    )
    return rec


def summary(*, student) -> dict:
    counts = AttendanceRecord.objects.filter(student=student).values("status").annotate(n=Count("id"))
    by_status = {row["status"]: row["n"] for row in counts}
    total = sum(by_status.values())
    present = by_status.get(AttendanceRecord.Status.PRESENT, 0)
    return {
        "present": present,
        "absent": by_status.get(AttendanceRecord.Status.ABSENT, 0),
        "leave": by_status.get(AttendanceRecord.Status.LEAVE, 0),
        "total": total,
        "percentage": round(present / total * 100, 1) if total else 0.0,
    }

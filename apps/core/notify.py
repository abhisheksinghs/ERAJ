"""Alerts to parents and staff (ADR-005).

Until the SMS/WhatsApp/email adapters land (M7) every alert is written to the
audit log and the application log, so staging shows exactly what would have
been sent and to whom. Callers never depend on delivery succeeding.
"""
import logging

from apps.core.audit import record

log = logging.getLogger("eraj.notify")


def guardian(student, event: str, message: str) -> None:
    """Alert the student's primary guardian (falls back to any guardian)."""
    links = list(student.guardian_links.select_related("guardian").all())
    link = next((g for g in links if g.is_primary), links[0] if links else None)
    phone = link.guardian.phone if link else ""
    log.info("notify guardian student=%s event=%s phone=%s: %s", student.pk, event, phone or "-", message)
    record("notify.guardian", event=event, student=student.pk, phone=phone, message=message)

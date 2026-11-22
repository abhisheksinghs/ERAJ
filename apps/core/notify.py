"""Alerts to parents and staff — the two call sites every module uses (ADR-005, ADR-011).

They keep their original signatures; delivery goes through `apps.notify` (templates, channels,
quiet hours, opt-out, delivery log). A failure to raise an alert never breaks the caller.
"""
import logging

from apps.core.audit import record

log = logging.getLogger("eraj.notify")


def guardian(student, event: str, message: str, **context) -> None:
    """Alert the student's primary guardian (falls back to any guardian)."""
    phone = _phone(student)
    log.info("notify guardian student=%s event=%s phone=%s: %s", student.pk, event, phone or "-", message)
    record("notify.guardian", event=event, student=student.pk, phone=phone, message=message)
    try:
        from django.db import transaction

        from apps.notify.services import raise_event

        with transaction.atomic():  # savepoint: a failure here can't poison the caller's transaction
            raise_event(branch=student.branch, event=event, student=student, context={"message": message, **context})
    except Exception:  # pragma: no cover — alerting must never break the business action
        log.exception("notify guardian failed event=%s student=%s", event, student.pk)


def staff_role(branch, role: str, event: str, message: str) -> None:
    """Alert every user holding `role` in `branch` (e.g. the transport in-charge, the store keeper)."""
    from apps.org.models import RoleAssignment

    emails = sorted(RoleAssignment.objects.filter(branch=branch, role=role).values_list("user__email", flat=True))
    log.info("notify role=%s branch=%s event=%s to=%s: %s", role, branch.pk, event, ",".join(emails) or "-", message)
    record("notify.staff", event=event, branch=branch.pk, role=role, to=emails, message=message)
    try:
        from django.db import transaction

        from apps.notify.services import raise_event

        with transaction.atomic():
            raise_event(branch=branch, event=event, role=role, context={"message": message})
    except Exception:  # pragma: no cover
        log.exception("notify staff failed event=%s role=%s", event, role)


def staff_users(users, event: str, message: str, *, branch, **context) -> None:
    """Alert particular staff logins (e.g. a section's class teacher)."""
    users = [u for u in users if u is not None]
    log.info("notify users=%s event=%s: %s", ",".join(u.email for u in users) or "-", event, message)
    record("notify.staff", event=event, branch=branch.pk, to=[u.email for u in users], message=message)
    try:
        from django.db import transaction

        from apps.notify.services import raise_event

        with transaction.atomic():
            raise_event(branch=branch, event=event, users=users, context={"message": message, **context})
    except Exception:  # pragma: no cover
        log.exception("notify users failed event=%s", event)


def _phone(student) -> str:
    links = list(student.guardian_links.select_related("guardian").all())
    link = next((g for g in links if g.is_primary), links[0] if links else None)
    return link.guardian.phone if link else ""

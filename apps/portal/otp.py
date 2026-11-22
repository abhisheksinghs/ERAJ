"""Portal OTP login (ADR-011). The request step always answers the same way, so it can't be used
to find out which numbers are registered."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.portal.access import digits, guardians_with_phone
from apps.portal.models import PortalOTP

log = logging.getLogger("eraj.portal")

LIFETIME = timedelta(minutes=5)
WINDOW = timedelta(minutes=15)
PER_WINDOW = 3
MAX_TRIES = 5
GENERIC = "If this number is registered with the school, a login code has been sent to it."


def _hash(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}:{settings.SECRET_KEY}".encode()).hexdigest()


def _students_for(phone10: str):
    from apps.people.models import Student

    return [s for s in Student.objects.filter(status=Student.Status.ACTIVE, guardian_links__guardian__in=_guardians(phone10)).distinct()]


def _guardians(phone10: str):
    return list(guardians_with_phone(phone10).values_list("pk", flat=True))


def _echo_allowed(branch) -> bool:
    """Staging only: return the code in the response when PORTAL_OTP_ECHO=1 and no real channel could deliver it."""
    if os.environ.get("PORTAL_OTP_ECHO") != "1":
        return False
    from apps.notify.models import ChannelConfig

    return not ChannelConfig.objects.filter(branch=branch, enabled=True).exclude(provider="log_only").exists()


def request_code(*, phone: str, ip: str | None = None) -> dict:
    p = digits(phone)
    out = {"detail": GENERIC}
    if not p:
        return out
    now = timezone.now()
    with transaction.atomic():
        recent = PortalOTP.objects.select_for_update().filter(phone=p, created_at__gte=now - WINDOW)
        if len(list(recent)) >= PER_WINDOW:
            record("portal.otp_throttled", actor=f"phone:{p[-4:]}", ip=ip or "")
            return out
        students = _students_for(p)
        if not students:
            record("portal.otp_unknown", actor=f"phone:{p[-4:]}", ip=ip or "")
            return out
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(8)
        PortalOTP.objects.create(phone=p, code_hash=_hash(code, salt), salt=salt, expires_at=now + LIFETIME, ip=ip)
    from apps.notify.services import raise_event

    branch = students[0].branch
    school = getattr(connection.tenant, "name", "") or branch.name
    with transaction.atomic():
        raise_event(branch=branch, event="portal.otp", to_phone=p, context={"code": code, "school": school})
    record("portal.otp_sent", actor=f"phone:{p[-4:]}", ip=ip or "")
    if _echo_allowed(branch):
        out["demo_code"] = code
    return out


def verify_code(*, phone: str, code: str):
    """Returns the portal User for this phone, creating it (and parent roles) on first login.
    A wrong try is saved before refusing, so the 5-try limit holds."""
    p = digits(phone)
    user, reason, attempt = _check(p, (code or "").strip())
    if user is None:
        record("portal.otp_failed", actor=f"phone:{p[-4:]}", reason=reason, attempt=attempt)
        raise Conflict("The code is wrong or has expired. Ask for a new one.")
    record("portal.login", actor=user.email)
    return user


@transaction.atomic
def _check(p: str, code: str):
    now = timezone.now()
    otp = (PortalOTP.objects.select_for_update().filter(phone=p, used_at__isnull=True, expires_at__gt=now)
           .order_by("-created_at").first()) if p else None
    if otp is None or otp.attempts >= MAX_TRIES:
        return None, "none-or-locked", otp.attempts if otp else 0
    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash(code, otp.salt)):
        otp.save(update_fields=["attempts"])
        return None, "mismatch", otp.attempts
    otp.used_at = now
    otp.save(update_fields=["attempts", "used_at"])
    PortalOTP.objects.filter(phone=p, used_at__isnull=True).update(used_at=now)  # one login per code burst
    return ensure_parent(p), "", otp.attempts


def ensure_parent(phone10: str):
    from apps.accounts.models import User
    from apps.org.models import Role, RoleAssignment
    from apps.people.models import Guardian

    user = User.objects.filter(phone=phone10, email__endswith="@parents.eraj.local").first()
    if user is None:
        user = User(email=f"p{phone10}@parents.eraj.local", phone=phone10)
        user.set_unusable_password()
        user.save()
    guardians = list(Guardian.objects.filter(pk__in=_guardians(phone10)).select_related("user"))
    if guardians:
        names = sorted({g.full_name for g in guardians})
        first, _, last = names[0].partition(" ")
        if not user.first_name:
            user.first_name, user.last_name = first[:150], last[:150]
            user.save(update_fields=["first_name", "last_name"])
        if not any(g.user_id == user.pk for g in guardians):
            free = next((g for g in guardians if g.user_id is None), None)
            if free is not None:
                Guardian.objects.filter(pk=free.pk).update(user=user)
    for b in {s.branch_id for s in _students_for(phone10)}:
        RoleAssignment.objects.get_or_create(user=user, role=Role.PARENT, branch_id=b)
    return user

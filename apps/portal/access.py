"""Who may see which child (ADR-011, PORTAL-5).

A portal caller sees exactly: their own student row (student login), and the students linked to a
guardian whose registered mobile is the caller's verified mobile. Anything else is a 404 — the
same answer as a student that does not exist, so ids can't be probed.
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework.exceptions import NotFound

from apps.people.models import Guardian, Student


def digits(phone: str) -> str:
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def guardians_with_phone(phone10: str):
    """Guardian rows store phones in several shapes (98…, +91 98765 …, 098…); compare digits only, last 10."""
    from django.db.models import F, Func, Value

    if not phone10:
        return Guardian.objects.none()
    only_digits = Func(F("phone"), Value(r"\D"), Value(""), Value("g"), function="regexp_replace")
    return Guardian.objects.annotate(phone_digits=only_digits).filter(phone_digits__endswith=phone10)


def guardians_for(user):
    if not (user and user.is_authenticated):
        return Guardian.objects.none()
    return guardians_with_phone(digits(getattr(user, "phone", "")))


def children_qs(user):
    if not (user and user.is_authenticated):
        return Student.objects.none()
    gids = [g.pk for g in guardians_for(user)]
    return (Student.objects.filter(Q(user=user) | Q(guardian_links__guardian_id__in=gids), status=Student.Status.ACTIVE)
            .distinct().select_related("branch").order_by("full_name"))


def child_for(request, pk) -> Student:
    """The child `pk` if the caller may see it AND it belongs to the request's branch; else 404."""
    from apps.org.scope import resolve_scope

    try:
        pk = int(pk)
    except (TypeError, ValueError) as exc:
        raise NotFound() from exc
    child = children_qs(request.user).filter(pk=pk).first()
    if child is None or child.branch_id not in resolve_scope(request).branch_ids:
        raise NotFound()
    return child


def is_self(request, child) -> bool:
    """Is the caller the student themself (student login), not a parent?"""
    return child.user_id is not None and child.user_id == request.user.pk


def guardian_rows(request, child):
    p = digits(request.user.phone)
    return [link.guardian for link in child.guardian_links.select_related("guardian") if p and digits(link.guardian.phone) == p]

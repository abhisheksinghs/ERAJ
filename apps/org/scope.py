"""
Resolve which branch(es) a request may touch (ADR-001).

The frontend proxy sends `X-Branch: <branch id>` (or `all` for a read-only,
group-level view). The value is only a *choice*; it is always checked against
the user's role assignments here, server-side.
"""
from __future__ import annotations

from dataclasses import dataclass

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import SAFE_METHODS

from apps.org.models import Branch, Role, RoleAssignment

HEADER = "HTTP_X_BRANCH"
ALL = "all"


@dataclass(frozen=True)
class BranchScope:
    branch_ids: frozenset[int]  # rows this request may read
    active: Branch | None  # where writes go; None for an all-branches read
    roles: frozenset[str]  # roles the user holds for this scope


def _assignments(user):
    return list(
        RoleAssignment.objects.filter(user=user).select_related("branch").order_by("pk")
    )


def allowed_branch_ids(user) -> set[int]:
    rows = _assignments(user)
    if any(r.branch_id is None for r in rows):  # group admin
        return set(Branch.objects.filter(is_active=True).values_list("id", flat=True))
    return {r.branch_id for r in rows if r.branch and r.branch.is_active and r.branch.deleted_at is None}


def roles_for(user, branch_id: int | None) -> set[str]:
    """Roles that apply in `branch_id`; `None` means the all-branches scope,
    where only branch-spanning (group) roles apply."""
    rows = _assignments(user)
    spanning = {r.role for r in rows if r.branch_id is None}
    if branch_id is None:
        return spanning
    return spanning | {r.role for r in rows if r.branch_id == branch_id}


def resolve_scope(request) -> BranchScope:
    cached = getattr(request, "_branch_scope", None)
    if cached is not None:
        return cached

    user = request.user
    allowed = allowed_branch_ids(user)
    raw = (request.META.get(HEADER) or "").strip()

    if raw.lower() == ALL:
        roles = roles_for(user, None)
        if Role.GROUP_ADMIN not in roles:
            raise PermissionDenied("Only a group admin can view all branches together.")
        if request.method not in SAFE_METHODS:
            raise PermissionDenied("Choose a single branch to make changes.")
        scope = BranchScope(frozenset(allowed), None, frozenset(roles))
    else:
        if raw:
            try:
                branch_id = int(raw)
            except ValueError as exc:
                raise ValidationError({"branch": "X-Branch must be a branch id or 'all'."}) from exc
            if branch_id not in allowed:
                raise PermissionDenied("You do not have access to this branch.")
        elif len(allowed) == 1:
            branch_id = next(iter(allowed))
        else:
            raise ValidationError({"branch": "Choose a branch (send the X-Branch header)."})
        branch = Branch.objects.get(pk=branch_id)
        scope = BranchScope(frozenset({branch_id}), branch, frozenset(roles_for(user, branch_id)))

    request._branch_scope = scope
    return scope

"""
`HasPerm` — the only permission class module ViewSets use (ADR-006).

Default deny: a ViewSet without `perm_resource`, or an unsafe custom action
without an entry in `action_perms`, is refused. `tests/test_router_guards.py`
fails the build for either, so a missing declaration is caught before deploy.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.org.rbac import roles_allow
from apps.org.scope import resolve_scope

READ_ACTIONS = {"list", "retrieve", "metadata"}
WRITE_ACTIONS = {"create", "update", "partial_update", "destroy"}


def required_perm(view, method: str) -> str | None:
    action = getattr(view, "action", None)
    explicit = getattr(view, "action_perms", {}) or {}
    if action in explicit:
        return explicit[action]
    resource = getattr(view, "perm_resource", None)
    if not resource:
        return None
    if action in READ_ACTIONS or (action is None and method in SAFE_METHODS):
        return f"{resource}.view"
    if action in WRITE_ACTIONS:
        return f"{resource}.manage"
    if method in SAFE_METHODS:  # read-only custom action (report, lookup, summary …)
        return f"{resource}.view"
    return None  # unsafe custom action with no declared permission → deny


class HasPerm(BasePermission):
    message = "Your role does not allow this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        perm = required_perm(view, request.method)
        if perm is None:
            return False
        scope = resolve_scope(request)
        return roles_allow(set(scope.roles), perm)

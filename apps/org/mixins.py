"""
ViewSet mixins every module uses (ADR-001, ADR-006).

    class BookViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
        perm_resource = "library.book"
        action_perms = {"waive": "library.fine.waive"}

`BranchScopedViewSetMixin` must come BEFORE the DRF ViewSet class so its
`get_queryset` / `perform_create` wrap DRF's.
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied

from apps.org.permissions import HasPerm
from apps.org.scope import resolve_scope


class PermissionedViewSetMixin:
    """For data that is not branch-owned (academic years, the branch list)."""

    permission_classes = [HasPerm]
    perm_resource: str = ""
    action_perms: dict[str, str] = {}


class BranchScopedViewSetMixin(PermissionedViewSetMixin):
    branch_field = "branch"

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):  # OpenAPI schema generation, no real user
            return qs.none()
        scope = resolve_scope(self.request)
        return qs.filter(**{f"{self.branch_field}_id__in": scope.branch_ids})

    def active_branch(self):
        scope = resolve_scope(self.request)
        if scope.active is None:
            raise PermissionDenied("Choose a single branch to make changes.")
        return scope.active

    def perform_create(self, serializer):
        serializer.save(**{self.branch_field: self.active_branch()})

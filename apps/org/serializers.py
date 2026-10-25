"""
Serializer helpers that keep foreign keys inside the caller's branch.

Without this, a user in branch A could POST `{"student": <id from branch B>}`
and DRF's default `PrimaryKeyRelatedField` would accept it, because the
related queryset is unfiltered. `ScopedPrimaryKeyRelatedField` limits writes to
the active branch and reads to the branches in scope.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.org.models import Branch, BranchOwned
from apps.org.scope import resolve_scope


class ScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        qs = super().get_queryset()
        request = self.context.get("request")
        if request is None or not issubclass(qs.model, BranchOwned):
            return qs
        scope = resolve_scope(request)
        ids = {scope.active.pk} if scope.active is not None else set(scope.branch_ids)
        return qs.filter(branch_id__in=ids)


class BranchScopedSerializer(serializers.ModelSerializer):
    """Base for every serializer of a branch-owned model. `branch` is read-only
    and stamped by the ViewSet."""

    serializer_related_field = ScopedPrimaryKeyRelatedField
    branch = serializers.PrimaryKeyRelatedField(read_only=True)


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ("id", "code", "name", "name_hi", "address", "phone", "email", "is_active")

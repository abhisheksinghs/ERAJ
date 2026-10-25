"""
Structural guards (ADR-001, ADR-006). These fail the build when someone adds a
ViewSet that would leak across branches or skip the permission check, before
any data exists to leak.

    python manage.py test apps.org.tests.test_router_guards
"""
from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import serializers

from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.models import BranchOwned
from apps.org.permissions import HasPerm
from apps.org.serializers import BranchScopedSerializer

UNSAFE = {"post", "put", "patch", "delete"}


def _viewsets(resolver=None):
    resolver = resolver or get_resolver("config.urls")
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _viewsets(entry)
        elif isinstance(entry, URLPattern):
            cls = getattr(entry.callback, "cls", None)
            if cls is not None and hasattr(entry.callback, "actions"):
                yield cls


def _model(cls):
    qs = getattr(cls, "queryset", None)
    if qs is not None:
        return qs.model
    ser = getattr(cls, "serializer_class", None)
    meta = getattr(ser, "Meta", None)
    return getattr(meta, "model", None)


class RouterGuardTest(SimpleTestCase):
    def setUp(self):
        self.classes = sorted(set(_viewsets()), key=lambda c: f"{c.__module__}.{c.__name__}")
        self.assertGreater(len(self.classes), 20, "router walk found too few ViewSets — guard is broken")

    def test_every_viewset_uses_hasperm_and_declares_a_resource(self):
        bad = [
            f"{c.__module__}.{c.__name__}"
            for c in self.classes
            if HasPerm not in getattr(c, "permission_classes", []) or not getattr(c, "perm_resource", "")
        ]
        self.assertEqual(bad, [], "ViewSets without HasPerm/perm_resource")

    def test_branch_owned_models_are_served_by_branch_scoped_viewsets(self):
        bad = []
        for c in self.classes:
            model = _model(c)
            if model is not None and issubclass(model, BranchOwned) and not issubclass(c, BranchScopedViewSetMixin):
                bad.append(f"{c.__module__}.{c.__name__} serves {model.__name__}")
        self.assertEqual(bad, [], "branch-owned data served without BranchScopedViewSetMixin")

    def test_unsafe_custom_actions_declare_a_permission(self):
        bad = []
        for c in self.classes:
            declared = getattr(c, "action_perms", {}) or {}
            for act in c.get_extra_actions():
                if set(act.mapping) & UNSAFE and act.__name__ not in declared:
                    bad.append(f"{c.__name__}.{act.__name__}")
        self.assertEqual(bad, [], "unsafe @action without an action_perms entry (would be denied)")

    def test_branch_owned_model_serializers_scope_their_foreign_keys(self):
        bad = []
        for c in self.classes:
            ser = getattr(c, "serializer_class", None)
            model = getattr(getattr(ser, "Meta", None), "model", None)
            if (
                ser is not None
                and issubclass(ser, serializers.ModelSerializer)
                and model is not None
                and issubclass(model, BranchOwned)
                and not issubclass(ser, BranchScopedSerializer)
            ):
                bad.append(f"{ser.__module__}.{ser.__name__}")
        self.assertEqual(bad, [], "ModelSerializers of branch-owned models must extend BranchScopedSerializer")

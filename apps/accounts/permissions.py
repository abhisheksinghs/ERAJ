"""Kept for import compatibility only. Module ViewSets use
`apps.org.permissions.HasPerm` (ADR-006); `role` on User no longer exists."""
from apps.org.permissions import HasPerm  # noqa: F401

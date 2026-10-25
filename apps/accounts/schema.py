"""Teach drf-spectacular that our JWT authentication is ordinary bearer JWT,
so the OpenAPI schema (and the typed frontend client) shows auth correctly."""
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class TenantBoundJWTScheme(SimpleJWTScheme):
    target_class = "apps.accounts.authentication.TenantBoundJWTAuthentication"
    name = "jwtAuth"

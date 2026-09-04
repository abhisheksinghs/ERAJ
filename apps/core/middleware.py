"""
Subscription + module-permission enforcement.

Runs after django-tenants' TenantMainMiddleware (so `request.tenant` and the
Postgres search_path are already set). Responsible for:

  1. Blocking all access if the tenant's subscription is suspended/terminated.
  2. Blocking access to a specific module if the current plan doesn't include
     it (e.g. request to /api/attendance/... on a Library-only plan).

Cache-backed (Redis) with a short TTL — see settings.MODULE_PERMISSION_CACHE_TTL
and docs/FAILURE_MODES.md ("Partial module downgrade not enforced") for why
this must NOT be baked into a long-lived JWT claim instead.
"""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

from apps.core.models import Client, Subscription

# Paths that are always allowed regardless of subscription state (health
# checks, the renewal/billing page itself — must not be gated by the thing
# it's meant to fix).
EXEMPT_PATH_PREFIXES = ("/health", "/api/billing/renew", "/admin")

# Maps a URL prefix to the module code that guards it. In a larger app this
# would be data-driven (per-app config) rather than hardcoded; kept explicit
# here for clarity.
MODULE_PATH_PREFIXES = {
    "/api/library": "library",
    "/api/hostel": "hostel",
    "/api/attendance": "attendance",
    "/api/hr": "hr",
    "/api/payroll": "payroll",
    "/api/fees": "fees",
    "/api/exam": "exam",
    "/api/transport": "transport",
    "/api/inventory": "inventory",
}


def _cache_key(schema_name: str) -> str:
    return f"subscription_state:{schema_name}"


def get_subscription_state(client: Client) -> dict:
    """
    Returns {"status": ..., "modules": [...]}, cached per-tenant.
    Cache is invalidated explicitly on subscription change
    (see apps/core/signals.py) — TTL is a backstop, not the primary
    invalidation mechanism.

    Deliberately queries `Subscription.objects.get(client=client)` instead
    of `client.subscription` — the reverse one-to-one accessor caches on the
    Python `client` instance itself, independent of the Redis cache below.
    If the caller holds a long-lived `client` object (e.g. across a Celery
    task and a later middleware call in the same process), `.subscription`
    can silently return stale data even after this function's own cache is
    invalidated. A fresh queryset avoids that second, invisible cache layer.
    """
    key = _cache_key(client.schema_name)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        subscription = Subscription.objects.select_related("plan").get(client=client)
    except Subscription.DoesNotExist:
        state = {"status": Subscription.Status.SUSPENDED, "modules": []}
    else:
        # granted_modules() is empty unless access is currently allowed, so an
        # unauthorized tenant has zero modules even if the 402 branch below is
        # ever refactored — the safe result is the default result.
        state = {
            "status": subscription.status,
            "modules": sorted(subscription.granted_modules()),
        }
    cache.set(key, state, timeout=settings.MODULE_PERMISSION_CACHE_TTL)
    return state


def invalidate_subscription_cache(client: Client) -> None:
    cache.delete(_cache_key(client.schema_name))


class SubscriptionEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        tenant = getattr(request, "tenant", None)
        # Public schema (superadmin) has no Client instance to check against.
        if tenant is None or not isinstance(tenant, Client) or tenant.schema_name == "public":
            return self.get_response(request)

        state = get_subscription_state(tenant)

        if state["status"] in (Subscription.Status.SUSPENDED, Subscription.Status.TERMINATED):
            return JsonResponse(
                {"error": "subscription_inactive", "status": state["status"]},
                status=402,  # Payment Required
            )

        for prefix, module_code in MODULE_PATH_PREFIXES.items():
            if request.path.startswith(prefix) and module_code not in state["modules"]:
                return JsonResponse(
                    {"error": "module_not_licensed", "module": module_code},
                    status=403,
                )

        return self.get_response(request)

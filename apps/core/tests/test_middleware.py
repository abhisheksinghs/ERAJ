"""
Unit tests for the subscription/module enforcement middleware, using
Django's RequestFactory (no real tenant schema switching needed — we
directly attach a `Client`/tenant object to the request and stub
get_subscription_state via the cache, since the middleware's job here is
pure request-routing logic, not schema resolution — that's covered by the
TenantTestCase-based integration tests in apps/library/tests/).
"""
import datetime

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from apps.core.middleware import (
    SubscriptionEnforcementMiddleware,
    get_subscription_state,
    invalidate_subscription_cache,
)
from apps.core.models import Client, Module, Plan, PlanModule, Subscription


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def tenant(db):
    return Client.objects.create(schema_name="mw_test_tenant", name="MW Test Tenant", slug="mw-test-tenant")


@pytest.fixture
def plan_with_library(db):
    plan = Plan.objects.create(name="Basic", price_per_year=30000)
    library = Module.objects.create(code="library", name="Library")
    PlanModule.objects.create(plan=plan, module=library)
    return plan


def make_request(path, tenant_obj):
    rf = RequestFactory()
    request = rf.get(path)
    request.tenant = tenant_obj
    return request


@pytest.mark.django_db
class TestSubscriptionEnforcementMiddleware:
    def test_blocks_all_access_when_subscription_missing(self, tenant):
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        response = middleware(make_request("/api/library/books/", tenant))
        assert response.status_code == 402

    def test_allows_licensed_module(self, tenant, plan_with_library):
        Subscription.objects.create(
            client=tenant,
            plan=plan_with_library,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
        )
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        response = middleware(make_request("/api/library/books/", tenant))
        assert response == "OK"

    def test_blocks_unlicensed_module(self, tenant, plan_with_library):
        """Plan includes library but not attendance — attendance must 403, not 402."""
        Subscription.objects.create(
            client=tenant,
            plan=plan_with_library,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
        )
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        response = middleware(make_request("/api/attendance/records/", tenant))
        assert response.status_code == 403

    def test_blocks_suspended_tenant_even_for_licensed_module(self, tenant, plan_with_library):
        Subscription.objects.create(
            client=tenant,
            plan=plan_with_library,
            status=Subscription.Status.SUSPENDED,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2025, 12, 31),
        )
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        response = middleware(make_request("/api/library/books/", tenant))
        assert response.status_code == 402

    def test_allows_grace_period_tenant(self, tenant, plan_with_library):
        """Grace period must behave like active for module access — it's a
        warning state, not a block, per the Subscription state machine."""
        Subscription.objects.create(
            client=tenant,
            plan=plan_with_library,
            status=Subscription.Status.GRACE_PERIOD,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2025, 12, 31),
        )
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        response = middleware(make_request("/api/library/books/", tenant))
        assert response == "OK"

    def test_exempt_paths_always_pass_through(self, tenant):
        """Health checks and the renewal page must work even when suspended —
        otherwise a suspended client can never see why or how to fix it."""
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        response = middleware(make_request("/health", tenant))
        assert response == "OK"

    def test_cache_reflects_downgrade_after_invalidation(self, tenant, plan_with_library):
        """
        Regression guard for docs/FAILURE_MODES.md ("Partial module
        downgrade not enforced"): after extra_modules/plan changes and an
        explicit cache invalidation, the NEXT request must see the new
        state — it must not be stuck serving stale cached permissions.
        """
        sub = Subscription.objects.create(
            client=tenant,
            plan=plan_with_library,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
        )
        middleware = SubscriptionEnforcementMiddleware(get_response=lambda r: "OK")
        assert middleware(make_request("/api/library/books/", tenant)) == "OK"

        # Downgrade: suspend the subscription, then explicitly invalidate
        # (this mirrors what the post_save signal does automatically).
        sub.status = Subscription.Status.SUSPENDED
        sub.save()
        invalidate_subscription_cache(tenant)

        response = middleware(make_request("/api/library/books/", tenant))
        assert response.status_code == 402

    def test_get_subscription_state_is_cached(self, tenant, plan_with_library, django_assert_num_queries):
        Subscription.objects.create(
            client=tenant,
            plan=plan_with_library,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
        )
        get_subscription_state(tenant)  # warms the cache
        with django_assert_num_queries(0):
            get_subscription_state(tenant)  # second call must be cache-only

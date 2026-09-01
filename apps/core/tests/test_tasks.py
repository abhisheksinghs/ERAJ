import datetime

import pytest

from apps.core.middleware import get_subscription_state
from apps.core.models import Client, Module, Plan, PlanModule, Subscription
from apps.core.tasks import recompute_all_subscription_statuses


@pytest.fixture
def plan(db):
    plan = Plan.objects.create(name="Basic", price_per_year=30000)
    library = Module.objects.create(code="library", name="Library")
    PlanModule.objects.create(plan=plan, module=library)
    return plan


@pytest.mark.django_db
class TestRecomputeSubscriptionStatuses:
    def test_expired_active_subscription_transitions_to_grace_period(self, plan):
        tenant = Client.objects.create(schema_name="expiring_tenant", name="Expiring Tenant", slug="expiring-tenant")
        sub = Subscription.objects.create(
            client=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date.today() - datetime.timedelta(days=1),  # expired yesterday
            grace_period_days=7,
        )
        result = recompute_all_subscription_statuses()

        sub.refresh_from_db()
        assert sub.status == Subscription.Status.GRACE_PERIOD
        assert (tenant.schema_name, Subscription.Status.GRACE_PERIOD) in result["updated"]

    def test_recompute_invalidates_stale_cache(self, plan):
        """
        The task must invalidate the Redis-cached permission state on any
        transition — otherwise a tenant that just got suspended keeps
        serving cached "active" responses until the TTL happens to expire.
        """
        tenant = Client.objects.create(schema_name="cache_test_tenant", name="Cache Test Tenant", slug="cache-test-tenant")
        sub = Subscription.objects.create(
            client=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date.today() - datetime.timedelta(days=30),
            grace_period_days=7,  # well past grace -> should suspend
        )
        # Warm the cache with the (soon to be stale) "active" state.
        get_subscription_state(tenant)

        recompute_all_subscription_statuses()

        # Cache must have been invalidated; a fresh read must reflect SUSPENDED.
        state = get_subscription_state(tenant)
        assert state["status"] == Subscription.Status.SUSPENDED

    def test_no_op_when_status_unchanged(self, plan):
        """Subscriptions still comfortably active must not be touched or
        trigger unnecessary cache invalidation/writes."""
        tenant = Client.objects.create(schema_name="stable_tenant", name="Stable Tenant", slug="stable-tenant")
        Subscription.objects.create(
            client=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date.today() + datetime.timedelta(days=300),
        )
        result = recompute_all_subscription_statuses()
        assert result["updated"] == []

"""
Unit tests for Subscription.recompute_status — the single source of truth
for the active -> grace_period -> suspended transition described in
docs/FAILURE_MODES.md ("Grace period ambiguity").

These use Django's test DB (pytest-django's `db` fixture) only to construct
model instances; the transition logic itself is a pure function of
(today, end_date, grace_period_days) so each case is a plain equality check.
"""
import datetime

import pytest

from apps.core.models import Client, Module, Plan, PlanModule, Subscription


@pytest.fixture
def client_obj(db):
    return Client.objects.create(schema_name="unit_test_client", name="Unit Test Client", slug="unit-test-client")


@pytest.fixture
def plan(db):
    return Plan.objects.create(name="Basic", price_per_year=30000)


@pytest.mark.django_db
class TestSubscriptionStateMachine:
    def _sub(self, client_obj, plan, end_date, grace_days=7):
        return Subscription(
            client=client_obj,
            plan=plan,
            start_date=end_date - datetime.timedelta(days=365),
            end_date=end_date,
            grace_period_days=grace_days,
        )

    def test_active_before_end_date(self, client_obj, plan):
        end_date = datetime.date(2026, 12, 31)
        sub = self._sub(client_obj, plan, end_date)
        assert sub.recompute_status(today=datetime.date(2026, 6, 1)) == Subscription.Status.ACTIVE

    def test_active_on_end_date_itself(self, client_obj, plan):
        """end_date is inclusive — the client's last paid day still counts as active."""
        end_date = datetime.date(2026, 12, 31)
        sub = self._sub(client_obj, plan, end_date)
        assert sub.recompute_status(today=end_date) == Subscription.Status.ACTIVE

    def test_grace_period_starts_day_after_end_date(self, client_obj, plan):
        end_date = datetime.date(2026, 12, 31)
        sub = self._sub(client_obj, plan, end_date, grace_days=7)
        day_after = end_date + datetime.timedelta(days=1)
        assert sub.recompute_status(today=day_after) == Subscription.Status.GRACE_PERIOD

    def test_grace_period_ends_exactly_at_boundary(self, client_obj, plan):
        end_date = datetime.date(2026, 12, 31)
        sub = self._sub(client_obj, plan, end_date, grace_days=7)
        last_grace_day = end_date + datetime.timedelta(days=7)
        assert sub.recompute_status(today=last_grace_day) == Subscription.Status.GRACE_PERIOD

    def test_suspended_one_day_after_grace_period(self, client_obj, plan):
        end_date = datetime.date(2026, 12, 31)
        sub = self._sub(client_obj, plan, end_date, grace_days=7)
        first_suspended_day = end_date + datetime.timedelta(days=8)
        assert sub.recompute_status(today=first_suspended_day) == Subscription.Status.SUSPENDED

    def test_zero_grace_period_suspends_immediately(self, client_obj, plan):
        """A client on a plan with no grace period at all."""
        end_date = datetime.date(2026, 12, 31)
        sub = self._sub(client_obj, plan, end_date, grace_days=0)
        assert sub.recompute_status(today=end_date + datetime.timedelta(days=1)) == Subscription.Status.SUSPENDED

    def test_terminated_is_never_auto_changed(self, client_obj, plan):
        """TERMINATED is a manual contractual action — the time-based function
        must not move a terminated subscription back to active/grace/suspended
        even if today is well within the paid period."""
        sub = self._sub(client_obj, plan, datetime.date(2026, 12, 31))
        sub.status = Subscription.Status.TERMINATED
        assert sub.recompute_status(today=datetime.date(2026, 1, 1)) == Subscription.Status.TERMINATED

    def test_granted_modules_empty_unless_access_allowed(self, client_obj, plan):
        library = Module.objects.create(code="library", name="Library")
        PlanModule.objects.create(plan=plan, module=library)
        sub = self._sub(client_obj, plan, datetime.date(2026, 12, 31))
        sub.save()

        sub.status = Subscription.Status.ACTIVE
        assert sub.granted_modules() == {"library"}
        sub.status = Subscription.Status.SUSPENDED
        assert sub.granted_modules() == set()

    def test_is_access_allowed_true_for_active_and_grace(self, client_obj, plan):
        sub = self._sub(client_obj, plan, datetime.date(2026, 12, 31))
        sub.status = Subscription.Status.ACTIVE
        assert sub.is_access_allowed() is True
        sub.status = Subscription.Status.GRACE_PERIOD
        assert sub.is_access_allowed() is True

    def test_is_access_allowed_false_for_suspended_and_terminated(self, client_obj, plan):
        sub = self._sub(client_obj, plan, datetime.date(2026, 12, 31))
        sub.status = Subscription.Status.SUSPENDED
        assert sub.is_access_allowed() is False
        sub.status = Subscription.Status.TERMINATED
        assert sub.is_access_allowed() is False

    def test_active_modules_combines_plan_and_extra_modules(self, client_obj, plan):
        library = Module.objects.create(code="library", name="Library")
        addon = Module.objects.create(code="transport", name="Transport")
        PlanModule.objects.create(plan=plan, module=library)

        sub = self._sub(client_obj, plan, datetime.date(2026, 12, 31))
        sub.save()
        sub.extra_modules.add(addon)

        assert sub.active_modules() == {"library", "transport"}

    def test_active_modules_does_not_imply_access_allowed(self, client_obj, plan):
        """
        Regression guard for the exact bug class this split is meant to
        prevent: active_modules() must NOT be used as a proxy for "can
        this tenant get in" — that's is_access_allowed()'s job.
        """
        library = Module.objects.create(code="library", name="Library")
        PlanModule.objects.create(plan=plan, module=library)

        sub = self._sub(client_obj, plan, datetime.date(2026, 12, 31))
        sub.status = Subscription.Status.SUSPENDED
        sub.save()

        assert "library" in sub.active_modules()  # plan still lists it...
        assert sub.is_access_allowed() is False  # ...but access must be denied

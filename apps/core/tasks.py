"""
Background tasks.

Rule enforced throughout this file (see docs/FAILURE_MODES.md, "Task loses
tenant context"): every task that touches tenant data takes the tenant's
schema_name as an explicit argument and enters it via `schema_context`.
Nothing relies on request-thread-local tenant state surviving into a Celery
worker process — it doesn't, by design, since workers are separate processes
picking tasks off a broker queue.
"""
from celery import shared_task
from django_tenants.utils import schema_context

from apps.core.middleware import invalidate_subscription_cache
from apps.core.models import Client, Subscription


@shared_task
def recompute_all_subscription_statuses() -> dict:
    """
    Daily job: walks every tenant's Subscription and applies the deterministic
    state-machine transition (active -> grace_period -> suspended). Runs from
    the public schema since Subscription is a SHARED_APPS model.
    """
    updated = []
    for subscription in Subscription.objects.select_related("client").all():
        new_status = subscription.recompute_status()
        if new_status != subscription.status:
            subscription.status = new_status
            subscription.save(update_fields=["status", "updated_at"])
            invalidate_subscription_cache(subscription.client)
            updated.append((subscription.client.schema_name, new_status))
    return {"updated": updated}


@shared_task
def generate_fees_report(schema_name: str, report_month: str) -> str:
    """
    Example of a tenant-scoped task. `schema_name` is passed explicitly by
    the caller (never inferred) so this task is safe to run on any worker,
    in any order, regardless of what the last task on this worker touched.
    """
    with schema_context(schema_name):
        client = Client.objects.get(schema_name=schema_name)  # sanity check tenant still exists
        # ... generate report using tenant-scoped models (Fees app) here ...
        return f"Report generated for {client.name} — {report_month}"

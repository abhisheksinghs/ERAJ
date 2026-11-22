"""Celery tasks for alerts (ADR-011). Every task takes the tenant schema explicitly
(docs/FAILURE_MODES.md, "Task loses tenant context")."""
from celery import shared_task
from django_tenants.utils import get_tenant_model, schema_context

from apps.notify import providers


@shared_task(bind=True, max_retries=4)
def send_message(self, schema_name: str, message_id: int):
    from apps.notify import services

    with schema_context(schema_name):
        try:
            return services.send_now(message_id).status
        except providers.Transient as exc:
            if self.request.retries >= self.max_retries:
                services.mark_failed_after_retries(message_id, str(exc))
                return "failed"
            if self.request.is_eager:  # tests / inline mode: retry now instead of scheduling
                return send_message.apply(args=(schema_name, message_id), retries=self.request.retries + 1).result
            raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries)


def _tenants():
    return [t.schema_name for t in get_tenant_model().objects.exclude(schema_name="public")]


@shared_task
def release_held_all() -> dict:
    from apps.notify import services

    out = {}
    for schema in _tenants():
        with schema_context(schema):
            out[schema] = services.release_held()
    return out


@shared_task
def daily_reminders_all() -> dict:
    from apps.notify import services
    from apps.org.models import Branch

    out = {}
    for schema in _tenants():
        with schema_context(schema):
            for b in Branch.objects.filter(is_active=True):
                out[f"{schema}:{b.code}"] = services.daily_reminders(b)
    return out

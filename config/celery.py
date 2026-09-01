import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("eraj")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.update(
    # A stuck task must not pin a worker forever.
    task_time_limit=300,
    task_soft_time_limit=270,
    # Re-queue a task if the worker dies mid-run instead of losing it.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Guard against slow leaks in long-lived workers.
    worker_max_tasks_per_child=100,
    # Don't keep results in Redis forever.
    result_expires=timedelta(hours=6),
)

app.conf.beat_schedule = {
    "recompute-subscription-statuses-daily": {
        "task": "apps.core.tasks.recompute_all_subscription_statuses",
        "schedule": crontab(hour=0, minute=5),  # 00:05 IST daily
    },
}
# NOTE: run exactly ONE beat process (see docs/DEPLOY.md) — two schedulers means
# every periodic task fires twice.

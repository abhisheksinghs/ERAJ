import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("eraj")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "recompute-subscription-statuses-daily": {
        "task": "apps.core.tasks.recompute_all_subscription_statuses",
        "schedule": crontab(hour=0, minute=5),  # 00:05 IST daily
    },
}

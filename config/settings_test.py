"""Test settings — same as production settings but points at the same DB
(django-tenants test runner creates/tears down schemas per test run)."""
from .settings import *  # noqa: F401,F403

DEBUG = False

DATABASES["default"]["TEST"] = {"NAME": "test_eraj_platform"}  # noqa: F405

# Alerts: run Celery tasks inline and keep email in memory (ADR-011 tests).
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

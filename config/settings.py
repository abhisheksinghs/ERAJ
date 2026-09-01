"""
Django settings for Eraj — a multi-tenant SaaS platform.

Architecture: schema-per-tenant via django-tenants.
Every request is routed to a Postgres schema based on the resolved tenant
(subdomain). SHARED_APPS live in the `public` schema (core platform:
tenants, plans, subscriptions, users, superadmin). TENANT_APPS live in
each tenant's own schema (library, hostel, attendance, ...).
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

from config.env_guard import INSECURE_SECRET, check_production_safety

BASE_DIR = Path(__file__).resolve().parent.parent

# dev | staging | prod. Drives the DEBUG default and the security lockdown below.
DJANGO_ENV = config("DJANGO_ENV", default="dev")
IS_PRODUCTION = DJANGO_ENV in ("staging", "prod")

SECRET_KEY = config("DJANGO_SECRET_KEY", default=INSECURE_SECRET)
DEBUG = config("DEBUG", default=not IS_PRODUCTION, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,.localhost", cast=Csv())

check_production_safety(is_production=IS_PRODUCTION, debug=DEBUG, secret_key=SECRET_KEY)

# ---------------------------------------------------------------------------
# django-tenants: this is the load-bearing config for the whole architecture.
# ---------------------------------------------------------------------------
SHARED_APPS = [
    "django_tenants",  # must be first
    "apps.core",  # Client (tenant), Domain, Plan, Module, Subscription live here
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "rest_framework",
]

TENANT_APPS = [
    "django.contrib.contenttypes",
    "apps.library",
    "apps.hostel",
]

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = "core.Client"  # app.Model that inherits TenantMixin
TENANT_DOMAIN_MODEL = "core.Domain"  # app.Model that inherits DomainMixin

DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

# django-tenants ships its own TestCase (TenantTestCase) that creates a real
# tenant schema per test class using the standard Django test runner — no
# custom TEST_RUNNER needed in this version. Fast pure-unit tests that don't
# touch tenant schemas run under pytest instead (see pytest.ini) — see
# docs/TESTING.md for the split.

MIDDLEWARE = [
    # TenantMainMiddleware MUST run first: it resolves the tenant from the
    # request's host header and sets the Postgres search_path for the
    # connection BEFORE any other middleware or view code touches the DB.
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files in production without a separate web server.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Subscription + module-permission gate. Runs AFTER tenant resolution
    # (needs request.tenant) and BEFORE views execute.
    "apps.core.middleware.SubscriptionEnforcementMiddleware",
]

ROOT_URLCONF = "config.urls"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"  # superadmin/public routes

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database: django_tenants.postgresql_backend wraps psycopg2 and manages the
# search_path per-connection based on the resolved tenant schema.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": config("DB_NAME", default="eraj_platform"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="postgres"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        # CONN_MAX_AGE > 0 with pgbouncer in transaction-pooling mode is the
        # #1 real-world django-tenants footgun: a pooled connection can be
        # reused across tenants if search_path isn't reset per-transaction.
        # See docs/FAILURE_MODES.md ("search_path + connection pooling").
        # Keep CONN_MAX_AGE=0 unless pgbouncer is configured in SESSION
        # pooling mode (not transaction mode) with search_path reset.
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=0, cast=int),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Security. This is what `manage.py check --deploy` asks for. The strict
# transport settings switch on only in staging/prod so plain-http local dev
# keeps working.
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
# Comma-separated, e.g. "https://*.eraj.com". Needed once the browser posts to
# Django directly (Phase 1 auth); harmless empty until then.
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # TLS terminates at the platform router
    SECURE_HSTS_SECONDS = 31_536_000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# REST framework / JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}

SIMPLE_JWT = {
    # Short access-token lifetime is a deliberate control: it bounds how
    # long a client can keep using a module after their subscription is
    # downgraded/expired mid-session. See docs/FAILURE_MODES.md
    # ("Race condition on expiry").
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
}

# ---------------------------------------------------------------------------
# Cache (Redis) — used for tenant/module-permission lookups so we don't hit
# Postgres on every request across 9 modules.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
    }
}
# TTL for cached module-permission/subscription-state lookups. Short on
# purpose — see docs/FAILURE_MODES.md ("Partial module downgrade not
# enforced").
MODULE_PERMISSION_CACHE_TTL = config("MODULE_PERMISSION_CACHE_TTL", default=180, cast=int)

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://127.0.0.1:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE

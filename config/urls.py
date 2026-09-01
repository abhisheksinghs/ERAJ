"""Tenant-schema URLconf (abc.eraj.com, xyz.eraj.com, ...).

No Django admin here — tenant staff use the API. The admin is public-schema
only (config/urls_public.py), behind MFA.
"""
from django.urls import include, path

from config.health import live, ready

urlpatterns = [
    path("health", live),
    path("health/ready", ready),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/library/", include("apps.library.urls")),
    path("api/hostel/", include("apps.hostel.urls")),
]

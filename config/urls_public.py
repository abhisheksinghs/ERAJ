"""Public-schema URLconf: superadmin (MFA-gated Django admin) + health.

The admin lives here and ONLY here — never on a tenant subdomain. Path is
`superadmin/`, off the guessable `/admin/` default.
"""
from django.urls import path

from config.admin import admin_site
from config.health import live, ready

urlpatterns = [
    path("health", live),
    path("health/ready", ready),
    path("superadmin/", admin_site.urls),
]

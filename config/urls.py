"""Tenant-schema URLconf (abc.eraj.com, xyz.eraj.com, ...).

No Django admin here — tenant staff use the API. The admin is public-schema
only (config/urls_public.py), behind MFA.
"""
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.health import live, ready

urlpatterns = [
    path("health", live),
    path("health/ready", ready),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/library/", include("apps.library.urls")),
    path("api/hostel/", include("apps.hostel.urls")),
    path("api/attendance/", include("apps.attendance.urls")),
    path("api/hr/", include("apps.hr.urls")),
    path("api/payroll/", include("apps.payroll.urls")),
    path("api/fees/", include("apps.fees.urls")),
    path("api/exam/", include("apps.exam.urls")),
    path("api/transport/", include("apps.transport.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
]

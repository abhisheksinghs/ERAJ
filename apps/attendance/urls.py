from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.attendance import devices, views

router = DefaultRouter()
router.register("settings", views.AttendanceSettingsViewSet, basename="attendance-settings")
router.register("holidays", views.HolidayViewSet, basename="holiday")
router.register("records", views.AttendanceRecordViewSet, basename="attendance-record")
router.register("reports", views.AttendanceReportViewSet, basename="attendance-report")
router.register("devices", views.AttendanceDeviceViewSet, basename="attendance-device")
router.register("cards", views.AttendanceCardViewSet, basename="attendance-card")
router.register("punches", views.PunchViewSet, basename="punch")

urlpatterns = [path("push/", devices.json_push, name="attendance-push"), *router.urls]

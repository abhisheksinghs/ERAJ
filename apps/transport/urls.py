from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.transport import gps, views

router = DefaultRouter()
router.register("routes", views.RouteViewSet, basename="transport-route")
router.register("stops", views.StopViewSet, basename="transport-stop")
router.register("fare-slabs", views.FareSlabViewSet, basename="transport-fare-slab")
router.register("vehicles", views.VehicleViewSet, basename="transport-vehicle")
router.register("documents", views.VehicleDocumentViewSet, basename="transport-document")
router.register("assignments", views.TransportAssignmentViewSet, basename="transport-assignment")
router.register("settings", views.TransportSettingsViewSet, basename="transport-settings")
router.register("alerts", views.TransportAlertViewSet, basename="transport-alert")
router.register("reports", views.TransportReportViewSet, basename="transport-report")

urlpatterns = [path("gps/push/", gps.push, name="transport-gps-push"), *router.urls]

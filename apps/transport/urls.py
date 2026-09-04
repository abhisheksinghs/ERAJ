from rest_framework.routers import DefaultRouter

from apps.transport import views

router = DefaultRouter()
router.register("routes", views.RouteViewSet, basename="transport-route")
router.register("vehicles", views.VehicleViewSet, basename="transport-vehicle")
router.register("assignments", views.TransportAssignmentViewSet, basename="transport-assignment")

urlpatterns = router.urls

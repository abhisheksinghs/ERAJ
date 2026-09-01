from rest_framework.routers import DefaultRouter

from apps.hostel import views

router = DefaultRouter()
router.register("rooms", views.RoomViewSet, basename="room")
router.register("residents", views.ResidentViewSet, basename="resident")
router.register("allocations", views.AllocationViewSet, basename="allocation")
router.register("waitlist", views.WaitlistViewSet, basename="waitlist")
router.register("maintenance", views.MaintenanceTicketViewSet, basename="maintenance")

urlpatterns = router.urls

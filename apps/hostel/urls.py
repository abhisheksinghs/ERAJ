from rest_framework.routers import DefaultRouter

from apps.hostel import views

router = DefaultRouter()
router.register("blocks", views.BlockViewSet, basename="block")
router.register("rooms", views.RoomViewSet, basename="room")
router.register("fee-rules", views.HostelFeeRuleViewSet, basename="fee-rule")
router.register("allocations", views.AllocationViewSet, basename="allocation")
router.register("waitlist", views.WaitlistViewSet, basename="waitlist")
router.register("maintenance", views.MaintenanceTicketViewSet, basename="maintenance")
router.register("messes", views.MessViewSet, basename="mess")
router.register("menu", views.MenuItemViewSet, basename="menu")
router.register("mess-members", views.MessMemberViewSet, basename="mess-member")
router.register("mess-leave", views.MessLeaveViewSet, basename="mess-leave")
router.register("mess-rebates", views.MessRebateViewSet, basename="mess-rebate")
router.register("guest-meals", views.GuestMealViewSet, basename="guest-meal")
router.register("meal-counts", views.MealCountViewSet, basename="meal-count")
router.register("mess-complaints", views.MessComplaintViewSet, basename="mess-complaint")
router.register("visitors", views.ApprovedVisitorViewSet, basename="visitor")
router.register("visits", views.VisitViewSet, basename="visit")
router.register("outpasses", views.OutpassViewSet, basename="outpass")

urlpatterns = router.urls

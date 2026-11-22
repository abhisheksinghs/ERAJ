from rest_framework.routers import DefaultRouter

from apps.hr import views

router = DefaultRouter()
router.register("designations", views.DesignationViewSet, basename="hr-designation")
router.register("profiles", views.StaffProfileViewSet, basename="hr-profile")
router.register("documents", views.StaffDocumentViewSet, basename="hr-document")
router.register("attendance", views.StaffAttendanceViewSet, basename="hr-attendance")
router.register("leave-types", views.LeaveTypeViewSet, basename="hr-leave-type")
router.register("balances", views.LeaveBalanceViewSet, basename="hr-balance")
router.register("leave", views.LeaveApplicationViewSet, basename="hr-leave")
router.register("staff", views.HRStaffViewSet, basename="hr-staff")
router.register("reports", views.HRReportViewSet, basename="hr-report")
router.register("me", views.MyHRViewSet, basename="hr-me")

urlpatterns = router.urls

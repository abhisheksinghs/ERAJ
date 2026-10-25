from rest_framework.routers import DefaultRouter

from apps.fees import views

router = DefaultRouter()
router.register("settings", views.FeeSettingsViewSet, basename="fee-settings")
router.register("heads", views.FeeHeadViewSet, basename="fee-head")
router.register("plans", views.FeePlanViewSet, basename="fee-plan")
router.register("charges", views.ChargeViewSet, basename="fee-charge")
router.register("concessions", views.ConcessionViewSet, basename="fee-concession")
router.register("receipts", views.ReceiptViewSet, basename="fee-receipt")
router.register("refunds", views.RefundViewSet, basename="fee-refund")
router.register("accounts", views.StudentAccountViewSet, basename="fee-account")
router.register("reports", views.FeeReportViewSet, basename="fee-report")

urlpatterns = router.urls

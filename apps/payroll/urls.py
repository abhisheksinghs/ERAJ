from rest_framework.routers import DefaultRouter

from apps.payroll import views

router = DefaultRouter()
router.register("payslips", views.PayslipViewSet, basename="payslip")

urlpatterns = router.urls

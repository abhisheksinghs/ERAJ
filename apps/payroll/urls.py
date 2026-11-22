from rest_framework.routers import DefaultRouter

from apps.payroll import views

router = DefaultRouter()
router.register("rule-sets", views.PayRuleSetViewSet, basename="payroll-rule-set")
router.register("levels", views.PayLevelViewSet, basename="payroll-level")
router.register("da-rates", views.DARateViewSet, basename="payroll-da-rate")
router.register("components", views.PayComponentViewSet, basename="payroll-component")
router.register("settings", views.StatutorySettingsViewSet, basename="payroll-settings")
router.register("structures", views.SalaryStructureViewSet, basename="payroll-structure")
router.register("loans", views.LoanViewSet, basename="payroll-loan")
router.register("one-time", views.OneTimePaymentViewSet, basename="payroll-one-time")
router.register("runs", views.PayrollRunViewSet, basename="payroll-run")
router.register("payslips", views.PayslipViewSet, basename="payroll-payslip")
router.register("reports", views.PayrollReportViewSet, basename="payroll-report")
router.register("me", views.MyPayslipViewSet, basename="payroll-me")

urlpatterns = router.urls

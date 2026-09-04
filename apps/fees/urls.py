from rest_framework.routers import DefaultRouter

from apps.fees import views

router = DefaultRouter()
router.register("structures", views.FeeStructureViewSet, basename="fee-structure")
router.register("payments", views.PaymentViewSet, basename="fee-payment")

urlpatterns = router.urls

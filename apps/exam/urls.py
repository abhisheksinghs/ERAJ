from rest_framework.routers import DefaultRouter

from apps.exam import views

router = DefaultRouter()
router.register("results", views.ExamResultViewSet, basename="exam-result")

urlpatterns = router.urls

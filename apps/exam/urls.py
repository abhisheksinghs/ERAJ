from rest_framework.routers import DefaultRouter

from apps.exam import views

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="exam-student")
router.register("subjects", views.SubjectViewSet, basename="exam-subject")
router.register("results", views.ExamResultViewSet, basename="exam-result")

urlpatterns = router.urls

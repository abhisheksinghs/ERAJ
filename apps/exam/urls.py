from rest_framework.routers import DefaultRouter

from apps.exam import views

router = DefaultRouter()
router.register("scales", views.GradeScaleViewSet, basename="grade-scale")
router.register("exams", views.ExamViewSet, basename="exam")
router.register("exam-subjects", views.ExamSubjectViewSet, basename="exam-subject")
router.register("marks", views.MarksViewSet, basename="marks")
router.register("results", views.ResultViewSet, basename="exam-result")

urlpatterns = router.urls

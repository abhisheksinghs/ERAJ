from rest_framework.routers import DefaultRouter

from apps.learning import views

router = DefaultRouter()
router.register("homework", views.HomeworkViewSet, basename="learning-homework")
router.register("submissions", views.SubmissionViewSet, basename="learning-submission")
router.register("materials", views.MaterialViewSet, basename="learning-material")
router.register("classes", views.OnlineClassViewSet, basename="learning-class")
router.register("tests", views.OnlineTestViewSet, basename="learning-test")
router.register("diary", views.DiaryViewSet, basename="learning-diary")
router.register("reports", views.LearningReportViewSet, basename="learning-report")

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from apps.attendance import views

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="attendance-student")
router.register("records", views.AttendanceRecordViewSet, basename="attendance-record")

urlpatterns = router.urls

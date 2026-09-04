from rest_framework.routers import DefaultRouter

from apps.hr import views

router = DefaultRouter()
router.register("departments", views.DepartmentViewSet, basename="hr-department")
router.register("employees", views.EmployeeViewSet, basename="hr-employee")

urlpatterns = router.urls

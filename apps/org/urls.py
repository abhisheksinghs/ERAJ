from rest_framework.routers import DefaultRouter

from apps.org import views

router = DefaultRouter()
router.register("branches", views.BranchViewSet, basename="branch")
router.register("users", views.UserViewSet, basename="user")

urlpatterns = router.urls

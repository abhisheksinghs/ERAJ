from rest_framework.routers import DefaultRouter

from apps.inventory import views

router = DefaultRouter()
router.register("items", views.ItemViewSet, basename="inventory-item")
router.register("issues", views.IssueRecordViewSet, basename="inventory-issue")

urlpatterns = router.urls

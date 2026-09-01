from rest_framework.routers import DefaultRouter

from apps.library import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("books", views.BookViewSet, basename="book")
router.register("members", views.MemberViewSet, basename="member")
router.register("issues", views.IssueViewSet, basename="issue")
router.register("fines", views.FineViewSet, basename="fine")
router.register("holds", views.HoldViewSet, basename="hold")

urlpatterns = router.urls

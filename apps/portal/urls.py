from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.portal import views

router = DefaultRouter()
router.register("children", views.ChildViewSet, basename="portal-child")
router.register("leaves", views.StudentLeaveViewSet, basename="portal-leave")
router.register("change-requests", views.ChangeRequestViewSet, basename="portal-change")
router.register("student-logins", views.StudentLoginViewSet, basename="portal-student-login")

urlpatterns = [
    path("otp/request/", views.OtpRequestView.as_view(), name="portal-otp-request"),
    path("otp/verify/", views.OtpVerifyView.as_view(), name="portal-otp-verify"),
    path("me/", views.MeView.as_view(), name="portal-me"),
    *router.urls,
]

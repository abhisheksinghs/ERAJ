from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.notify import views

router = DefaultRouter()
router.register("channels", views.ChannelConfigViewSet, basename="notify-channel")
router.register("settings", views.NotifySettingsViewSet, basename="notify-settings")
router.register("rules", views.AlertRuleViewSet, basename="notify-rule")
router.register("templates", views.TemplateViewSet, basename="notify-template")
router.register("opt-outs", views.OptOutViewSet, basename="notify-optout")
router.register("messages", views.MessageViewSet, basename="notify-message")
router.register("notices", views.NoticeViewSet, basename="notify-notice")

urlpatterns = [
    path("webhooks/whatsapp/", views.whatsapp_webhook, name="notify-whatsapp-webhook"),
    path("webhooks/sms/", views.sms_dlr, name="notify-sms-dlr"),
    *router.urls,
]

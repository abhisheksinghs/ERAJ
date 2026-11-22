import hashlib
import hmac
import json
import os
from datetime import datetime, timezone as dt_tz

from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notify import catalogue, services
from apps.notify.models import AlertRule, Channel, ChannelConfig, Message, Notice, NotifySettings, OptOut, Template
from apps.notify.serializers import (
    AlertRuleSerializer, ChannelConfigSerializer, MessageSerializer, NoticeSerializer, NotifySettingsSerializer,
    OptOutSerializer, TemplateSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.scope import resolve_scope


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


class _EnsureRows:
    """Settings-like lists: make sure the active branch's rows exist before listing."""

    def ensure(self, branch):  # pragma: no cover — overridden
        pass

    def list(self, request, *args, **kwargs):
        if resolve_scope(request).active is not None:
            self.ensure(resolve_scope(request).active)
        return super().list(request, *args, **kwargs)


class ChannelConfigViewSet(_EnsureRows, BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = ChannelConfig.objects.all()
    serializer_class = ChannelConfigSerializer
    perm_resource = "notify.channel"

    def ensure(self, branch):
        for ch in Channel:
            services.config_for(branch, ch)


class NotifySettingsViewSet(_EnsureRows, BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = NotifySettings.objects.all()
    serializer_class = NotifySettingsSerializer
    perm_resource = "notify.settings"

    def ensure(self, branch):
        services.settings_for(branch)


class AlertRuleViewSet(_EnsureRows, BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    perm_resource = "notify.rule"
    filterset_fields = ["enabled"]

    def ensure(self, branch):
        for ev in catalogue.EVENTS.values():
            if ev.audience == "direct":
                continue
            AlertRule.objects.get_or_create(branch=branch, event=ev.key,
                                            defaults={"enabled": ev.enabled, "channels": list(ev.channels)})


class TemplateViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    perm_resource = "notify.template"
    filterset_fields = ["event", "channel", "language"]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def defaults(self, request):
        """The built-in wording per event (what is sent until a template overrides it)."""
        return Response([{"event": e.key, "label": e.label, "en": e.en, "hi": e.hi} for e in catalogue.EVENTS.values()])


class OptOutViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin,
                    viewsets.GenericViewSet):
    queryset = OptOut.objects.select_related("guardian")
    serializer_class = OptOutSerializer
    perm_resource = "notify.optout"
    search_fields = ["guardian__full_name", "guardian__phone"]


class MessageViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Message.objects.select_related("student")
    serializer_class = MessageSerializer
    perm_resource = "notify.message"
    action_perms = {"retry": "notify.message.manage"}
    filterset_fields = {"event": ["exact"], "channel": ["exact"], "status": ["exact"], "student": ["exact"],
                        "notice": ["exact"], "created_at": ["date__gte", "date__lte"]}
    search_fields = ["to", "recipient_name", "body"]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def monthly(self, request):
        return Response(services.monthly_counts(self.active_branch()))

    @extend_schema(request=None, responses=MessageSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        m = self.get_object()
        if m.status != Message.Status.FAILED:
            from apps.core.exceptions import Conflict

            raise Conflict("Only a failed message can be retried.")
        Message.objects.filter(pk=m.pk).update(status=Message.Status.QUEUED, error="")
        m.refresh_from_db()
        services._queue([m])
        return Response(MessageSerializer(m, context={"request": request}).data)


class NoticeViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = NoticeSerializer
    perm_resource = "notify.notice"
    action_perms = {"send": "notify.notice.manage"}
    filterset_fields = ["audience"]

    def get_queryset(self):
        self.queryset = Notice.objects.annotate(read_count=Count("reads"))
        return super().get_queryset()

    def perform_destroy(self, instance):
        from apps.core.exceptions import Conflict

        if instance.sent_at:
            raise Conflict("A sent notice stays on record.")
        instance.delete()

    @extend_schema(request=None, responses=NoticeSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        n = services.send_notice(notice=self.get_object(), by=who(request))
        n = Notice.objects.annotate(read_count=Count("reads")).get(pk=n.pk)
        return Response(NoticeSerializer(n, context={"request": request}).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def reads(self, request, pk=None):
        n = self.get_object()
        read = {r.student_id: r.read_at for r in n.reads.all()}
        return Response({"recipients": n.recipients, "read": len(read),
                         "rows": [{"student": s.pk, "name": s.full_name, "admission_no": s.admission_no,
                                   "read_at": read.get(s.pk)} for s in n.students.order_by("full_name")]})


# ------------------------------------------------------------------ provider webhooks (no JWT)
def _check_signature(body: bytes, header: str) -> bool:
    secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


@csrf_exempt
def whatsapp_webhook(request):
    """Meta Cloud API: GET verification handshake; POST message status updates."""
    if request.method == "GET":
        token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        if token and request.GET.get("hub.mode") == "subscribe" and hmac.compare_digest(request.GET.get("hub.verify_token", ""), token):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse("forbidden", status=403)
    if request.method != "POST":
        return JsonResponse({"detail": "GET or POST."}, status=405)
    if not _check_signature(request.body, request.headers.get("X-Hub-Signature-256", "")):
        return JsonResponse({"detail": "Bad signature."}, status=403)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"detail": "Bad JSON."}, status=400)
    n = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for st in (change.get("value") or {}).get("statuses", []):
                err = "; ".join(f"{e.get('code')}: {e.get('title') or e.get('message')}" for e in st.get("errors", []))
                at = datetime.fromtimestamp(int(st.get("timestamp", 0) or 0), tz=dt_tz.utc) if st.get("timestamp") else None
                n += services.apply_receipt(provider_ref=st.get("id", ""), status=st.get("status", ""), error=err, at=at)
    return JsonResponse({"updated": n})


@csrf_exempt
def sms_dlr(request):
    """Generic SMS delivery report: ?token=…&ref=…&status=delivered|failed&reason=… (GET or POST form)."""
    data = request.POST if request.method == "POST" else request.GET
    token = os.environ.get("SMS_DLR_TOKEN", "")
    if not token or not hmac.compare_digest(data.get("token", ""), token):
        return JsonResponse({"detail": "forbidden"}, status=403)
    status = {"delivrd": "delivered", "delivered": "delivered", "success": "delivered", "failed": "failed",
              "undeliv": "failed", "rejected": "failed", "expired": "failed"}.get(data.get("status", "").lower(), "")
    n = services.apply_receipt(provider_ref=data.get("ref", ""), status=status, error=data.get("reason", "")) if status else 0
    return JsonResponse({"updated": n})

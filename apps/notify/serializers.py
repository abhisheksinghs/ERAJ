from rest_framework import serializers

from apps.notify import catalogue
from apps.notify.models import AlertRule, Channel, ChannelConfig, Message, Notice, NotifySettings, OptOut, Template
from apps.org.serializers import BranchScopedSerializer

CHANNELS = [c.value for c in Channel]


class ChannelConfigSerializer(BranchScopedSerializer):
    credential_set = serializers.SerializerMethodField()

    class Meta:
        model = ChannelConfig
        fields = ("id", "branch", "channel", "provider", "enabled", "sender", "endpoint", "credential_env", "credential_set")
        read_only_fields = ("channel",)

    def get_credential_set(self, obj) -> bool:
        import os

        return bool(obj.credential_env and os.environ.get(obj.credential_env))

    def validate_credential_env(self, v):
        if v and not v.replace("_", "").isalnum():
            raise serializers.ValidationError("An environment variable NAME (letters, digits, _), not the secret itself.")
        return v.upper()

    def validate_endpoint(self, v):
        if v and not v.startswith("https://"):
            raise serializers.ValidationError("Use an https:// URL.")
        return v

    def validate(self, attrs):
        provider = attrs.get("provider", getattr(self.instance, "provider", None))
        channel = getattr(self.instance, "channel", None)
        fits = {"sms": {"log_only", "sms_http"}, "whatsapp": {"log_only", "whatsapp_cloud"}, "email": {"log_only", "smtp"}}
        if channel and provider not in fits[channel]:
            raise serializers.ValidationError({"provider": "That provider doesn't send this channel."})
        return attrs


class NotifySettingsSerializer(BranchScopedSerializer):
    class Meta:
        model = NotifySettings
        fields = ("id", "branch", "quiet_start", "quiet_end", "sms_fallback")


class AlertRuleSerializer(BranchScopedSerializer):
    label = serializers.SerializerMethodField()
    label_hi = serializers.SerializerMethodField()
    audience = serializers.SerializerMethodField()
    channels_text = serializers.SerializerMethodField()

    class Meta:
        model = AlertRule
        fields = ("id", "branch", "event", "label", "label_hi", "audience", "enabled", "channels", "channels_text", "days_before")
        read_only_fields = ("event",)

    def get_label(self, obj) -> str:
        return catalogue.get(obj.event).label

    def get_label_hi(self, obj) -> str:
        return catalogue.get(obj.event).label_hi

    def get_audience(self, obj) -> str:
        return catalogue.get(obj.event).audience

    def get_channels_text(self, obj) -> str:
        return ", ".join(obj.channels or [])

    def validate_channels(self, v):
        if not isinstance(v, list) or any(c not in CHANNELS for c in v):
            raise serializers.ValidationError(f"Choose from {', '.join(CHANNELS)}.")
        return list(dict.fromkeys(v))


class TemplateSerializer(BranchScopedSerializer):
    class Meta:
        model = Template
        fields = ("id", "branch", "event", "channel", "language", "body", "provider_template")

    def validate_event(self, v):
        if v not in catalogue.EVENTS:
            raise serializers.ValidationError("Unknown event.")
        return v

    def validate_body(self, v):
        import string

        try:
            list(string.Formatter().parse(v))
        except ValueError as exc:
            raise serializers.ValidationError("Unbalanced { } in the text.") from exc
        return v


class OptOutSerializer(BranchScopedSerializer):
    guardian_name = serializers.CharField(source="guardian.full_name", read_only=True)
    guardian_phone = serializers.CharField(source="guardian.phone", read_only=True)

    class Meta:
        model = OptOut
        fields = ("id", "branch", "guardian", "guardian_name", "guardian_phone", "channel", "created_at")
        read_only_fields = ("created_at",)


class MessageSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True, default=None)

    class Meta:
        model = Message
        fields = ("id", "branch", "event", "channel", "to", "recipient_name", "student", "student_name", "notice", "language",
                  "body", "status", "send_after", "provider", "provider_ref", "error", "attempts", "sent_at", "delivered_at",
                  "created_at")
        read_only_fields = fields

    def to_representation(self, obj):
        data = super().to_representation(obj)
        from apps.notify.services import SECRET_EVENTS, redact

        if obj.event in SECRET_EVENTS:  # still queued: the code is in the row, never on screen
            data["body"] = redact(data["body"])
        return data


class NoticeSerializer(BranchScopedSerializer):
    read_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Notice
        fields = ("id", "branch", "title", "body", "audience", "section", "program", "route", "block", "channels",
                  "sent_at", "sent_by", "recipients", "read_count", "created_at")
        read_only_fields = ("sent_at", "sent_by", "recipients", "created_at")

    def validate_channels(self, v):
        if not isinstance(v, list) or any(c not in CHANNELS for c in v):
            raise serializers.ValidationError(f"Choose from {', '.join(CHANNELS)}.")
        return v

    def validate(self, attrs):
        if self.instance is not None and self.instance.sent_at:
            raise serializers.ValidationError("A sent notice can't be edited.")
        return attrs

"""
Alerts (ADR-011). Branch-owned (ADR-001). `Message` is the delivery log every
alert and notice goes through; provider credentials are env var NAMES only.
"""
from __future__ import annotations

from datetime import time

from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class Channel(models.TextChoices):
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"
    EMAIL = "email", "Email"


class ChannelConfig(TimeStamped, BranchOwned):
    class Provider(models.TextChoices):
        LOG_ONLY = "log_only", "Log only (staging — nothing is sent)"
        SMS_HTTP = "sms_http", "SMS gateway (DLT, HTTP)"
        WHATSAPP_CLOUD = "whatsapp_cloud", "WhatsApp Business (Meta Cloud API)"
        SMTP = "smtp", "Email (SMTP)"

    channel = models.CharField(max_length=8, choices=Channel.choices)
    provider = models.CharField(max_length=14, choices=Provider.choices, default=Provider.LOG_ONLY)
    enabled = models.BooleanField(default=True)
    sender = models.CharField(max_length=120, blank=True,
                              help_text="DLT header / WhatsApp phone-number id / from address")
    endpoint = models.CharField(max_length=300, blank=True,
                                help_text="SMS gateway URL template: {to} {text} {sender} {template_id} {key}")
    credential_env = models.CharField(max_length=80, blank=True,
                                      help_text="Name of the server environment variable holding the API key / password")

    class Meta:
        ordering = ("channel",)
        constraints = [models.UniqueConstraint(fields=["branch", "channel"], name="notify_one_config_per_channel")]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} — {self.get_provider_display()}"


class NotifySettings(TimeStamped, BranchOwned):
    quiet_start = models.TimeField(default=time(21, 0))
    quiet_end = models.TimeField(default=time(7, 0))
    sms_fallback = models.BooleanField(default=True, help_text="When SMS is off, send SMS alerts by WhatsApp and email")

    class Meta:
        verbose_name_plural = "notify settings"
        constraints = [models.UniqueConstraint(fields=["branch"], name="notify_one_settings_per_branch")]


class AlertRule(TimeStamped, BranchOwned):
    event = models.CharField(max_length=40)
    enabled = models.BooleanField(default=True)
    channels = models.JSONField(default=list, help_text='e.g. ["sms", "whatsapp"]')
    days_before = models.PositiveSmallIntegerField(default=3, help_text="For 'fee due soon'")

    class Meta:
        ordering = ("event",)
        constraints = [models.UniqueConstraint(fields=["branch", "event"], name="notify_one_rule_per_event")]


class Template(TimeStamped, BranchOwned):
    event = models.CharField(max_length=40)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    language = models.CharField(max_length=2, choices=[("en", "English"), ("hi", "Hindi")], default="en")
    body = models.TextField(help_text="Placeholders in {braces}, e.g. {student} {date}")
    provider_template = models.CharField(max_length=80, blank=True, help_text="DLT template id / WhatsApp template name")

    class Meta:
        ordering = ("event", "channel", "language")
        constraints = [models.UniqueConstraint(fields=["branch", "event", "channel", "language"], name="notify_template_unique")]


class OptOut(TimeStamped, BranchOwned):
    guardian = models.ForeignKey("people.Guardian", on_delete=models.CASCADE, related_name="opt_outs")
    channel = models.CharField(max_length=8, choices=Channel.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["guardian", "channel"], name="notify_optout_unique")]


class Message(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        HELD = "held", "Held (quiet hours)"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        SIMULATED = "simulated", "Simulated (log only)"
        SKIPPED = "skipped", "Skipped"

    event = models.CharField(max_length=40, db_index=True)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    to = models.CharField(max_length=254, help_text="Phone or email")
    recipient_name = models.CharField(max_length=255, blank=True)
    guardian = models.ForeignKey("people.Guardian", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notice = models.ForeignKey("Notice", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    language = models.CharField(max_length=2, default="en")
    body = models.TextField()
    provider_template = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.QUEUED)
    send_after = models.DateTimeField(null=True, blank=True)
    provider = models.CharField(max_length=14, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True, db_index=True)
    error = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=120, blank=True)
    bypass_quiet = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["branch", "channel", "created_at"], name="notify_msg_branch_channel")]
        constraints = [
            models.UniqueConstraint(fields=["branch", "channel", "to", "dedupe_key"], condition=~Q(dedupe_key=""),
                                    name="notify_msg_dedupe"),
        ]


class Notice(TimeStamped, BranchOwned):
    class Audience(models.TextChoices):
        SECTION = "section", "One section"
        PROGRAM = "program", "A class / course (all sections)"
        ROUTE = "route", "A transport route"
        BLOCK = "block", "A hostel block"
        PARENTS = "parents", "All parents"
        STAFF = "staff", "All staff"

    title = models.CharField(max_length=150)
    body = models.TextField()
    audience = models.CharField(max_length=8, choices=Audience.choices)
    section = models.ForeignKey("people.Section", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    program = models.ForeignKey("people.Program", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    route = models.ForeignKey("transport.Route", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    block = models.ForeignKey("hostel.Block", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    channels = models.JSONField(default=list, blank=True, help_text="Also send by these channels; empty = portal only")
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.CharField(max_length=255, blank=True)
    recipients = models.PositiveIntegerField(default=0)
    students = models.ManyToManyField("people.Student", blank=True, related_name="notices",
                                      help_text="Resolved audience at sending time")

    class Meta:
        ordering = ("-created_at",)


class NoticeRead(models.Model):
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["notice", "user"], name="notify_read_once")]

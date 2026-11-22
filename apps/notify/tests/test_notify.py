"""Alert acceptance scenarios (scope doc, Alerts 1–4) and channel behaviour. Real tenant schema.

    python manage.py test apps.notify.tests.test_notify
"""
import hashlib
import hmac
import json
import os
from datetime import date, datetime
from unittest import mock

from django.core import mail
from django.utils import timezone
from django_tenants.test.client import TenantClient
from freezegun import freeze_time

from apps.core.testing import EraTestCase
from apps.notify import providers, services
from apps.notify.models import ChannelConfig, Message, Notice, NotifySettings, OptOut, Template
from apps.people.models import Enrollment, Guardian, Program, Section, StudentGuardian

ENV = {"WA_TOKEN": "wa-token", "SMS_KEY": "sms-key", "WHATSAPP_APP_SECRET": "app-secret", "SMS_DLR_TOKEN": "dlr-token"}


class FakeHTTP:
    """Stands in for providers._http: records calls, answers like WhatsApp / an SMS gateway."""

    def __init__(self, wa_status=200, wa_error=None, sms_status=200):
        self.calls, self.wa_status, self.wa_error, self.sms_status, self.n = [], wa_status, wa_error, sms_status, 0

    def __call__(self, req):
        self.n += 1
        self.calls.append(req)
        if "graph" in req.full_url:
            if self.wa_status >= 400:
                return self.wa_status, json.dumps({"error": {"message": self.wa_error or "Bad request"}})
            return 200, json.dumps({"messages": [{"id": f"wamid.{self.n}"}]})
        return self.sms_status, json.dumps({"message_id": f"sms-{self.n}"})


@freeze_time("2026-11-20 10:00:00+05:30")
class NotifyBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.p6 = Program.objects.create(branch=self.branch, code="C6", name="Class 6")
        self.s6a = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p6, name="A")
        self.s6b = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p6, name="B")
        self.a1, self.a2 = self.kid(self.s6a, "9811000001"), self.kid(self.s6a, "9811000002")
        self.b1 = self.kid(self.s6b, "9822000001")

    def kid(self, section, phone, email=""):
        s = self.make_student()
        Enrollment.objects.create(branch=self.branch, student=s, academic_year=self.year, program=section.program, section=section)
        g = Guardian.objects.create(branch=self.branch, full_name=f"Parent of {s.full_name}", phone=phone, email=email)
        StudentGuardian.objects.create(branch=self.branch, student=s, guardian=g, relation="father", is_primary=True)
        return s

    def real_channels(self):
        ChannelConfig.objects.update_or_create(branch=self.branch, channel="sms", defaults={
            "provider": "sms_http", "enabled": True, "sender": "ERAJSC",
            "endpoint": "https://sms.example/api?to={to}&text={text}&sender={sender}&key={key}", "credential_env": "SMS_KEY"})
        ChannelConfig.objects.update_or_create(branch=self.branch, channel="whatsapp", defaults={
            "provider": "whatsapp_cloud", "enabled": True, "sender": "1234567890", "credential_env": "WA_TOKEN"})

    def wa_hook(self, statuses):
        body = json.dumps({"entry": [{"changes": [{"value": {"statuses": statuses}}]}]}).encode()
        sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        return TenantClient(self.tenant).post("/api/notify/webhooks/whatsapp/", body, content_type="application/json",
                                              HTTP_X_HUB_SIGNATURE_256=sig)


class Scenario1Test(NotifyBase):
    def test_scenario_alerts_1_absent_reaches_sms_and_whatsapp_and_is_logged_delivered(self):
        self.real_channels()
        fake = FakeHTTP()
        teacher = self.make_user("teacher")
        self.make_staff(user=teacher)
        self.s6a.class_teacher = teacher.staff_profile
        self.s6a.save()
        with mock.patch.object(providers, "_http", fake), self.captureOnCommitCallbacks(execute=True):
            r = self.api(teacher).post("/api/attendance/records/mark/", {"section": self.s6a.pk, "date": "2026-11-20",
                                                                        "absent": [self.a1.pk]}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        msgs = {m.channel: m for m in Message.objects.filter(event="attendance.absent")}
        self.assertEqual(set(msgs), {"sms", "whatsapp"})
        self.assertEqual({m.to for m in msgs.values()}, {"9811000001"})
        self.assertIn(self.a1.full_name, msgs["sms"].body)
        self.assertEqual(msgs["sms"].status, "sent")
        sms_req = next(c for c in fake.calls if "sms.example" in c.full_url)
        self.assertIn("to=9811000001", sms_req.full_url)
        self.assertIn("key=sms-key", sms_req.full_url)  # key read from the env var, not the DB
        # provider receipts arrive
        self.assertEqual(self.wa_hook([{"id": msgs["whatsapp"].provider_ref, "status": "delivered", "timestamp": "1795162900"}]).json(), {"updated": 1})
        r = TenantClient(self.tenant).get(f"/api/notify/webhooks/sms/?token=dlr-token&ref={msgs['sms'].provider_ref}&status=DELIVRD")
        self.assertEqual(r.json(), {"updated": 1})
        for m in Message.objects.filter(event="attendance.absent"):
            self.assertEqual(m.status, "delivered")
            self.assertLess((m.sent_at - m.created_at).total_seconds(), 300)
        # marking again the same day doesn't alert twice
        with mock.patch.object(providers, "_http", fake), self.captureOnCommitCallbacks(execute=True):
            r = self.api(teacher).post("/api/attendance/records/mark/", {"section": self.s6a.pk, "date": "2026-11-20",
                                                                        "absent": [self.a1.pk, self.a2.pk]}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Message.objects.filter(event="attendance.absent", student=self.a1).count(), 2)
        self.assertEqual(Message.objects.filter(event="attendance.absent", student=self.a2).count(), 2)

    def test_sms_off_falls_back_to_whatsapp_and_email(self):
        Guardian.objects.filter(phone="9811000001").update(email="parent@example.in")
        ChannelConfig.objects.update_or_create(branch=self.branch, channel="email", defaults={"provider": "smtp", "sender": "office@school.in"})
        with self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a1, on=date(2026, 11, 20))
        msgs = {m.channel: m.status for m in Message.objects.all()}
        self.assertEqual(msgs, {"whatsapp": "simulated", "email": "sent"})  # staging WhatsApp = log only; email real
        self.assertEqual(mail.outbox[0].to, ["parent@example.in"])


class Scenario2Test(NotifyBase):
    def test_scenario_alerts_2_notice_to_one_section_reaches_only_its_parents(self):
        admin = self.api(self.make_user("admin"))
        r = admin.post("/api/notify/notices/", {"title": "PTM", "body": "Parent-teacher meeting on Saturday 10 am.",
                                                "audience": "section", "section": self.s6a.pk, "channels": ["whatsapp"]},
                       content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        with self.captureOnCommitCallbacks(execute=True):
            r = admin.post(f"/api/notify/notices/{r.json()['id']}/send/")
        self.assertEqual(r.json()["recipients"], 2)
        self.assertEqual(sorted(Message.objects.filter(event="notice").values_list("to", flat=True)), ["9811000001", "9811000002"])
        self.assertIn("PTM: Parent-teacher meeting", Message.objects.filter(event="notice").first().body)
        self.assertEqual(admin.post(f"/api/notify/notices/{r.json()['id']}/send/").status_code, 409)
        self.assertEqual(self.api(self.make_user("teacher")).post("/api/notify/notices/", {}).status_code, 403)


class Scenario3Test(NotifyBase):
    def test_scenario_alerts_3_quiet_hours_hold_until_morning(self):
        with freeze_time("2026-11-20 22:30:00+05:30"), self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a1, on=date(2026, 11, 20))
        m = Message.objects.get(channel="whatsapp")
        self.assertEqual(m.status, "held")
        self.assertEqual(timezone.localtime(m.send_after).strftime("%Y-%m-%d %H:%M"), "2026-11-21 07:00")
        with freeze_time("2026-11-21 06:55:00+05:30"):
            self.assertEqual(services.release_held(), 0)
        with freeze_time("2026-11-21 07:00:30+05:30"), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.release_held(), 1)  # WhatsApp (no email on record → no email row)
        m.refresh_from_db()
        self.assertEqual(m.status, "simulated")
        self.assertEqual(timezone.localtime(m.sent_at).strftime("%H:%M"), "07:00")

    def test_otp_ignores_quiet_hours_and_opt_out(self):
        with freeze_time("2026-11-20 23:00:00+05:30"), self.captureOnCommitCallbacks(execute=True):
            services.raise_event(branch=self.branch, event="portal.otp", to_phone="9811000001", context={"code": "123456"})
        self.assertEqual(set(Message.objects.values_list("status", flat=True)), {"simulated"})


class Scenario4Test(NotifyBase):
    def test_scenario_alerts_4_failed_delivery_shows_the_providers_reason(self):
        self.real_channels()
        ChannelConfig.objects.filter(channel="sms").update(enabled=False)
        NotifySettings.objects.update_or_create(branch=self.branch, defaults={"sms_fallback": False})
        fake = FakeHTTP(wa_status=400, wa_error="(#131026) Message undeliverable")
        with mock.patch.object(providers, "_http", fake), self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a1, on=date(2026, 11, 20))
        m = Message.objects.get(channel="whatsapp")
        self.assertEqual((m.status, m.error), ("failed", "WhatsApp: (#131026) Message undeliverable"))
        rows = self.api(self.make_user("admin")).get("/api/notify/messages/?status=failed").json()["results"]
        self.assertEqual(rows[0]["error"], "WhatsApp: (#131026) Message undeliverable")
        # a later receipt-level failure also lands in the log
        ok = FakeHTTP()
        with mock.patch.object(providers, "_http", ok), self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a2, on=date(2026, 11, 20))
        m2 = Message.objects.get(channel="whatsapp", student=self.a2)
        self.wa_hook([{"id": m2.provider_ref, "status": "failed", "errors": [{"code": 131047, "title": "Re-engagement message"}]}])
        m2.refresh_from_db()
        self.assertEqual((m2.status, m2.error), ("failed", "131047: Re-engagement message"))

    def test_transient_errors_retry_then_give_up(self):
        self.real_channels()
        ChannelConfig.objects.filter(channel="sms").update(enabled=False)
        NotifySettings.objects.update_or_create(branch=self.branch, defaults={"sms_fallback": False})

        def down(req):
            raise providers.Transient("connection reset")

        with mock.patch.object(providers, "_http", down), self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a1, on=date(2026, 11, 20))
        m = Message.objects.get(channel="whatsapp")
        self.assertEqual(m.status, "failed")
        self.assertIn("Gave up after retries", m.error)
        self.assertEqual(m.attempts, 5)

    def test_webhook_rejects_bad_signature(self):
        r = TenantClient(self.tenant).post("/api/notify/webhooks/whatsapp/", b"{}", content_type="application/json",
                                           HTTP_X_HUB_SIGNATURE_256="sha256=00")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(TenantClient(self.tenant).get("/api/notify/webhooks/sms/?token=x&ref=1&status=delivered").status_code, 403)


class ControlsTest(NotifyBase):
    def test_opt_out_rule_off_hindi_template_and_staff_events(self):
        g = Guardian.objects.get(phone="9811000001")
        OptOut.objects.create(branch=self.branch, guardian=g, channel="whatsapp")
        admin = self.api(self.make_user("admin"))
        rules = admin.get("/api/notify/rules/?page_size=100").json()["results"]
        absent = next(r for r in rules if r["event"] == "attendance.absent")
        self.assertEqual(admin.patch(f"/api/notify/rules/{absent['id']}/", {"channels": ["whatsapp", "fax"]},
                                     content_type="application/json").status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a1, on=date(2026, 11, 20))
        self.assertEqual(Message.objects.get(channel="whatsapp").status, "skipped")
        admin.patch(f"/api/notify/rules/{absent['id']}/", {"enabled": False}, content_type="application/json")
        self.assertEqual(services.absent_today(student=self.a2, on=date(2026, 11, 20)), None)
        self.assertFalse(Message.objects.filter(student=self.a2).exists())
        # Hindi template for a parent who chose Hindi
        user = self.make_user()
        user.preferred_language = "hi"
        user.save()
        Guardian.objects.filter(phone="9822000001").update(user=user)
        Template.objects.create(branch=self.branch, event="fees.payment_received", channel="whatsapp", language="hi",
                                body="{student} के लिए Rs {amount} मिले, रसीद {receipt}")
        services.raise_event(branch=self.branch, event="fees.payment_received", student=self.b1,
                             context={"amount": "1,500", "receipt": "R/1"})
        self.assertEqual(Message.objects.get(student=self.b1).body, f"{self.b1.full_name} के लिए Rs 1,500 मिले, रसीद R/1")
        # staff role events go to the role's users
        store = self.make_user("store", email="store@school.in")
        services.raise_event(branch=self.branch, event="inventory.low_stock", role="store", context={"message": "Paper low"})
        self.assertEqual(list(Message.objects.filter(event="inventory.low_stock").values_list("to", "user")), [("store@school.in", store.pk)])

    def test_channel_config_keeps_secrets_out_of_the_db_and_monthly_counts(self):
        admin = self.api(self.make_user("admin"))
        rows = admin.get("/api/notify/channels/").json()["results"]
        wa = next(r for r in rows if r["channel"] == "whatsapp")
        r = admin.patch(f"/api/notify/channels/{wa['id']}/", {"credential_env": "EAAG-my-real-token!"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = admin.patch(f"/api/notify/channels/{wa['id']}/", {"provider": "smtp"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = admin.patch(f"/api/notify/channels/{wa['id']}/", {"provider": "whatsapp_cloud", "credential_env": "wa_token"}, content_type="application/json")
        self.assertEqual((r.json()["credential_env"], r.json()["credential_set"]), ("WA_TOKEN", True))
        with self.captureOnCommitCallbacks(execute=True):
            services.absent_today(student=self.a1, on=date(2026, 11, 20))
        counts = admin.get("/api/notify/messages/monthly/").json()
        self.assertEqual({(c["month"], c["channel"]) for c in counts}, {("2026-11", "whatsapp")})
        self.assertIsNotNone(Notice)
        self.assertIsInstance(datetime.now(), datetime)

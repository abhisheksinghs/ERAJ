"""Parent & student portal acceptance scenarios (scope doc, Portal 1–5), OTP login, and the parent
half of Learning 1 (grade visible on the portal).

    python manage.py test apps.portal.tests.test_portal
"""
import os
import re
import shutil
import tempfile
from datetime import date
from decimal import Decimal as D
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django_tenants.test.client import TenantClient
from freezegun import freeze_time

from apps.core.testing import EraTestCase, access_token
from apps.exam import services as exam_services
from apps.exam.models import Exam, ExamSubject, GradeBand, GradeScale
from apps.fees import services as fee_services
from apps.fees.models import FeeHead
from apps.hostel import services as hostel_services
from apps.hostel.models import Block, Outpass, Room
from apps.learning.models import Homework
from apps.notify.models import Message, Notice
from apps.notify.services import send_notice
from apps.org.models import RoleAssignment
from apps.people.models import Enrollment, Guardian, Program, Section, StudentGuardian, Subject, TeachingAssignment
from apps.portal import otp
from apps.portal.models import ChangeRequest, PortalOTP, StudentLeave

TMP = tempfile.mkdtemp(prefix="eraj-portal-")
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
PHONE = "9876500001"


@override_settings(MEDIA_ROOT=TMP)
@freeze_time("2026-11-20 10:00:00+05:30")
class PortalBase(EraTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.north = self.make_branch("north")
        self.p6 = Program.objects.create(branch=self.branch, code="C6", name="Class 6")
        self.p8 = Program.objects.create(branch=self.north, code="C8", name="Class 8")
        self.t_user = self.make_user("teacher")
        self.teacher = self.make_staff(user=self.t_user, full_name="Anita Class")
        self.s6a = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p6, name="A", class_teacher=self.teacher)
        self.s8a = Section.objects.create(branch=self.north, academic_year=self.year, program=self.p8, name="A")
        self.maths = Subject.objects.create(branch=self.branch, code="C6-MAT", name="Maths", program=self.p6)
        TeachingAssignment.objects.create(branch=self.branch, staff=self.teacher, subject=self.maths, section=self.s6a)
        # one parent, two children in two branches (two guardian rows with the same mobile)
        self.riya = self.kid(self.s6a, "+91 98765 00001", "Riya Kumari", self.branch)
        self.aman = self.kid(self.s8a, "09876500001", "Aman Kumar", self.north)
        self.other = self.kid(self.s6a, "9811100002", "Other Child", self.branch)

    def kid(self, section, phone, name, branch):
        s = self.make_student(branch=branch, full_name=name)
        Enrollment.objects.create(branch=branch, student=s, academic_year=self.year, program=section.program, section=section)
        g = Guardian.objects.create(branch=branch, full_name="Sunita Devi" if "98765" in phone else f"Parent of {name}", phone=phone)
        StudentGuardian.objects.create(branch=branch, student=s, guardian=g, relation="mother", is_primary=True)
        return s

    def login(self, phone=PHONE):
        anon = TenantClient(self.tenant)
        with mock.patch.dict(os.environ, {"PORTAL_OTP_ECHO": "1"}):
            r = anon.post("/api/portal/otp/request/", {"phone": phone}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        r = anon.post("/api/portal/otp/verify/", {"phone": phone, "code": r.json()["demo_code"]}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    def portal(self, token, branch=None):
        h = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        if branch is not None:
            h["HTTP_X_BRANCH"] = str(branch.pk)
        return TenantClient(self.tenant, **h)

    def student_login(self, student):
        from apps.portal.services import create_student_login

        user = create_student_login(student=student, email=f"{student.admission_no.lower()}@students.test", password="Pa55word!x", by="office")
        return self.portal(access_token(user), student.branch)


class Scenario1Test(PortalBase):
    def test_scenario_portal_1_parent_with_two_children_logs_in_by_otp_and_switches(self):
        with self.captureOnCommitCallbacks(execute=True):  # let the (eager) send run, as the worker would
            token = self.login()
        me = self.portal(token).get("/api/portal/me/").json()
        self.assertEqual(me["kind"], "parent")
        self.assertEqual(sorted((c["name"], c["branch"]) for c in me["children"]),
                         [("Aman Kumar", self.north.pk), ("Riya Kumari", self.branch.pk)])
        riya = self.portal(token, self.branch).get(f"/api/portal/children/{self.riya.pk}/").json()
        aman = self.portal(token, self.north).get(f"/api/portal/children/{self.aman.pk}/").json()
        self.assertEqual((riya["child"]["name"], riya["child"]["section"]), ("Riya Kumari", str(self.s6a)))
        self.assertEqual((aman["child"]["name"], aman["child"]["section"]), ("Aman Kumar", str(self.s8a)))
        # a parent role in both branches; the code was sent by SMS/WhatsApp and is not readable in the log afterwards
        self.assertEqual(set(RoleAssignment.objects.filter(role="parent").values_list("branch_id", flat=True)), {self.branch.pk, self.north.pk})
        sent = Message.objects.filter(event="portal.otp")
        self.assertTrue(sent.exists())
        self.assertTrue(all(not re.search(r"\d{6}", m.body) for m in sent), [m.body for m in sent])
        self.assertFalse(PortalOTP.objects.filter(used_at__isnull=True).exists())

    def test_otp_request_does_not_reveal_unknown_numbers_and_is_rate_limited(self):
        anon = TenantClient(self.tenant)
        known = anon.post("/api/portal/otp/request/", {"phone": PHONE}, content_type="application/json").json()
        unknown = anon.post("/api/portal/otp/request/", {"phone": "9000000000"}, content_type="application/json").json()
        self.assertEqual(known, unknown)
        self.assertNotIn("demo_code", known)
        self.assertEqual(PortalOTP.objects.filter(phone="9000000000").count(), 0)
        for _ in range(4):
            otp.request_code(phone=PHONE)
        self.assertEqual(PortalOTP.objects.filter(phone=PHONE).count(), 3)  # 3 per 15 minutes

    def test_wrong_code_five_times_locks_and_expired_code_fails(self):
        with mock.patch.object(otp.secrets, "randbelow", return_value=123456):
            otp.request_code(phone=PHONE)
        anon = TenantClient(self.tenant)
        for _ in range(5):
            r = anon.post("/api/portal/otp/verify/", {"phone": PHONE, "code": "000000"}, content_type="application/json")
            self.assertEqual(r.status_code, 409)
        r = anon.post("/api/portal/otp/verify/", {"phone": PHONE, "code": "123456"}, content_type="application/json")
        self.assertEqual(r.status_code, 409)  # locked after 5 tries, even with the right code
        with freeze_time("2026-11-20 10:20:00+05:30"):
            with mock.patch.object(otp.secrets, "randbelow", return_value=654321):
                otp.request_code(phone=PHONE)
        with freeze_time("2026-11-20 10:26:00+05:30"):
            r = anon.post("/api/portal/otp/verify/", {"phone": PHONE, "code": "654321"}, content_type="application/json")
        self.assertEqual(r.status_code, 409)


class Scenario2Test(PortalBase):
    def test_scenario_portal_2_absent_mark_shows_on_portal_at_once(self):
        token = self.login()
        home = self.portal(token, self.branch).get(f"/api/portal/children/{self.riya.pk}/").json()
        self.assertIsNone(home["attendance_today"])
        r = self.api(self.t_user).post("/api/attendance/records/mark/", {"section": self.s6a.pk, "date": "2026-11-20",
                                                                        "absent": [self.riya.pk]}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        home = self.portal(token, self.branch).get(f"/api/portal/children/{self.riya.pk}/").json()
        self.assertEqual(home["attendance_today"], "absent")
        cal = self.portal(token, self.branch).get(f"/api/portal/children/{self.riya.pk}/attendance/?month=2026-11").json()
        self.assertEqual([d["statuses"] for d in cal["days"] if d["date"] == "2026-11-20"], [["absent"]])
        self.assertTrue(Message.objects.filter(event="attendance.absent", student=self.riya).exists())


class Scenario3Test(PortalBase):
    def test_scenario_portal_3_receipt_and_published_report_card_only(self):
        head = FeeHead.objects.create(branch=self.branch, code="TUI", name="Tuition", kind="tuition")
        fee_services.add_adjustment(student=self.riya, head=head, amount=D("2500"), description="November tuition",
                                    due_date=date(2026, 11, 10))
        receipt = fee_services.collect(student=self.riya, mode="cash", amount=D("1000"), received_by="acc")
        scale = GradeScale.objects.create(branch=self.branch, name="Simple")
        for grade, low in (("A", 75), ("B", 50), ("C", 33), ("E", 0)):
            GradeBand.objects.create(scale=scale, grade=grade, min_percent=low, is_fail=grade == "E")
        half = Exam.objects.create(branch=self.branch, name="Half-Yearly", academic_year=self.year, program=self.p6, scale=scale)
        final = Exam.objects.create(branch=self.branch, name="Annual", academic_year=self.year, program=self.p6, scale=scale, sequence=2)
        for e in (half, final):
            es = ExamSubject.objects.create(branch=self.branch, exam=e, subject=self.maths, max_theory=100, pass_marks=33)
            exam_services.save_marks(exam_subject=es, section=self.s6a, by="t",
                                     rows=[{"student": self.riya.pk, "theory": D(82), "status": "present"},
                                           {"student": self.other.pk, "theory": D(40), "status": "present"}])
        exam_services.publish(exam=half, by="admin")

        api = self.portal(self.login(), self.branch)
        fees = api.get(f"/api/portal/children/{self.riya.pk}/fees/").json()
        self.assertEqual((D(str(fees["paid"])), D(str(fees["outstanding"])), D(str(fees["overdue"]))), (D(1000), D(1500), D(1500)))
        r = api.get(f"/api/portal/children/{self.riya.pk}/receipt/?receipt={receipt.pk}")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        results = api.get(f"/api/portal/children/{self.riya.pk}/results/").json()
        self.assertEqual([(x["name"], x["grade"], x["result"]) for x in results], [("Half-Yearly", "A", "pass")])
        r = api.get(f"/api/portal/children/{self.riya.pk}/report-card/?exam={half.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(api.get(f"/api/portal/children/{self.riya.pk}/report-card/?exam={final.pk}").status_code, 404)
        # another child's receipt through my child's URL
        fee_services.add_adjustment(student=self.other, head=head, amount=D("500"), description="Nov", due_date=date(2026, 11, 10))
        theirs = fee_services.collect(student=self.other, mode="cash", amount=D("500"), received_by="acc")
        self.assertEqual(api.get(f"/api/portal/children/{self.riya.pk}/receipt/?receipt={theirs.pk}").status_code, 404)


class Scenario4Test(PortalBase):
    def test_scenario_portal_4_outpass_requested_by_parent_approved_by_warden(self):
        block = Block.objects.create(branch=self.branch, code="G", name="Girls block")
        room = Room.objects.create(branch=self.branch, block=block, number="101", capacity=2)
        hostel_services.allocate(student=self.riya, room=room)
        api = self.portal(self.login(), self.branch)
        r = api.post(f"/api/portal/children/{self.riya.pk}/outpass/", {"from_date": "2026-11-22", "to_date": "2026-11-23",
                                                                       "reason": "Cousin's wedding", "destination": "Patna"},
                     content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        op = Outpass.objects.get(pk=r.json()["id"])
        self.assertEqual(op.requested_by, "parent")
        warden = self.make_user("warden")
        r = self.api(warden).post(f"/api/hostel/outpasses/{op.pk}/approve/", {"note": "OK"}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        rows = api.get(f"/api/portal/children/{self.riya.pk}/outpasses/").json()["rows"]
        self.assertEqual([(x["id"], x["status"]) for x in rows], [(op.pk, "approved")])
        # a day scholar can't ask for an outpass
        r = api.post(f"/api/portal/children/{self.riya.pk}/leave/", {"from_date": "2026-11-24", "to_date": "2026-11-24", "reason": "x"},
                     content_type="application/json")
        self.assertEqual(r.status_code, 409)


class Scenario5Test(PortalBase):
    def test_scenario_portal_5_no_access_to_another_child_by_changing_the_url(self):
        token = self.login()
        api = self.portal(token, self.branch)
        self.assertEqual(api.get(f"/api/portal/children/{self.riya.pk}/").status_code, 200)
        self.assertEqual(api.get(f"/api/portal/children/{self.other.pk}/").status_code, 404)
        self.assertEqual(api.get("/api/portal/children/999999/").status_code, 404)
        # my other child, but asked in the wrong branch: refused too
        self.assertEqual(api.get(f"/api/portal/children/{self.aman.pk}/").status_code, 404)

    def test_idor_sweep_every_child_endpoint_refuses_another_child(self):
        from django.urls import reverse

        from apps.portal.views import ChildViewSet

        api = self.portal(self.login(), self.branch)
        query = "?receipt=1&exam=1&homework=1&file=1&material=1&attempt=1&month=2026-11"
        body = {"homework": 1, "online_class": 1, "test": 1, "attempt": 1, "notice": 1, "from_date": "2026-11-25",
                "to_date": "2026-11-25", "reason": "x", "field": "address", "new_value": "x"}
        routes = [("portal-child-detail", ["get"])] + [(f"portal-child-{a.url_name}", list(a.mapping)) for a in ChildViewSet.get_extra_actions()]
        self.assertGreater(len(routes), 25)
        for name, methods in routes:
            url = reverse(name, kwargs={"pk": self.other.pk})
            for method in methods:
                r = api.get(url + query) if method == "get" else api.post(url, body, content_type="application/json")
                self.assertEqual(r.status_code, 404, f"{method.upper()} {url} → {r.status_code}")
        self.assertEqual(StudentLeave.objects.count() + ChangeRequest.objects.count() + Outpass.objects.count(), 0)

    def test_staff_and_other_parents_see_no_children(self):
        token = self.login("9811100002")  # the other child's parent
        me = self.portal(token).get("/api/portal/me/").json()
        self.assertEqual([c["name"] for c in me["children"]], ["Other Child"])
        self.assertEqual(self.portal(token, self.branch).get(f"/api/portal/children/{self.riya.pk}/").status_code, 404)
        self.assertEqual(self.api(self.make_user("admin")).get(f"/api/portal/children/{self.riya.pk}/").status_code, 404)
        # a parent can't reach staff APIs
        self.assertEqual(self.portal(token, self.branch).get("/api/people/students/").status_code, 403)


class LearningOnPortalTest(PortalBase):
    def test_scenario_learning_1_parent_sees_the_grade_and_student_submits_from_portal(self):
        hw = Homework.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, teacher=self.teacher,
                                     title="Fractions", due_date=date(2026, 11, 22))
        student = self.student_login(self.riya)
        r = student.post(f"/api/portal/children/{self.riya.pk}/submit/",
                         {"homework": hw.pk, "text": "", "files": SimpleUploadedFile("page.jpg", JPG, content_type="image/jpeg")})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "submitted")
        sub = hw.submissions.get()
        self.api(self.t_user).post(f"/api/learning/submissions/{sub.pk}/grade/", {"grade": "A", "remarks": "Neat"},
                                   content_type="application/json")
        parent = self.portal(self.login(), self.branch)
        row = next(h for h in parent.get(f"/api/portal/children/{self.riya.pk}/homework/").json() if h["id"] == hw.pk)
        self.assertEqual((row["status"], row["grade"], row["remarks"]), ("checked", "A", "Neat"))
        # a parent can see but not submit on the child's behalf
        r = parent.post(f"/api/portal/children/{self.riya.pk}/submit/", {"homework": hw.pk, "text": "x"})
        self.assertEqual(r.status_code, 403)

    def test_student_takes_test_and_joins_class_on_portal(self):
        from apps.learning.models import OnlineClass, OnlineTest, Question

        t = OnlineTest.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, title="Quiz", published=True,
                                      opens_at=self._at("2026-11-20T09:00"), closes_at=self._at("2026-11-20T18:00"), time_limit_minutes=10)
        qs = [Question.objects.create(test=t, sequence=i, text=f"Q{i}", options=["a", "b"], correct=1) for i in range(1, 4)]
        c = OnlineClass.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, title="Live", link="https://meet.google.com/x",
                                       starts_at=self._at("2026-11-20T10:05"), ends_at=self._at("2026-11-20T10:45"))
        api = self.student_login(self.riya)
        start = api.post(f"/api/portal/children/{self.riya.pk}/start-test/", {"test": t.pk}, content_type="application/json").json()
        self.assertNotIn("correct", start["questions"][0])
        api.post(f"/api/portal/children/{self.riya.pk}/save-answers/", {"attempt": start["attempt"], "answers": {str(qs[0].pk): 1}},
                 content_type="application/json")
        done = api.post(f"/api/portal/children/{self.riya.pk}/finish-test/",
                        {"attempt": start["attempt"], "answers": {str(qs[0].pk): 1, str(qs[1].pk): 1, str(qs[2].pk): 0}},
                        content_type="application/json").json()
        self.assertEqual((D(str(done["score"])), D(str(done["max_score"]))), (D(2), D(3)))
        r = api.post(f"/api/portal/children/{self.riya.pk}/join/", {"online_class": c.pk}, content_type="application/json")
        self.assertEqual(r.json(), {"link": "https://meet.google.com/x"})
        classes = api.get(f"/api/portal/children/{self.riya.pk}/classes/").json()
        self.assertEqual([(x["id"], x["joined"], x["state"]) for x in classes], [(c.pk, True, "open")])
        self.assertEqual(self.api(self.t_user).get(f"/api/learning/classes/{c.pk}/joins/").json()["joined"], 1)

    def _at(self, s):
        from datetime import datetime

        from django.utils import timezone

        return timezone.make_aware(datetime.fromisoformat(s))


class RequestsTest(PortalBase):
    def test_day_scholar_leave_goes_to_class_teacher_and_marks_leave(self):
        api = self.portal(self.login(), self.branch)
        r = api.post(f"/api/portal/children/{self.riya.pk}/leave/", {"from_date": "2026-11-19", "to_date": "2026-11-21",
                                                                     "reason": "Fever"}, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        lv = r.json()["id"]
        teacher = self.api(self.t_user)
        self.assertEqual([x["id"] for x in teacher.get("/api/portal/leaves/").json()["results"]], [lv])
        other_teacher = self.make_user("teacher")
        self.make_staff(user=other_teacher)
        self.assertEqual(self.api(other_teacher).get("/api/portal/leaves/").json()["count"], 0)
        r = teacher.post(f"/api/portal/leaves/{lv}/decide/", {"approve": True}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        # past + today recorded as leave; marking the section later keeps her on leave
        from apps.attendance.models import AttendanceRecord

        self.assertEqual(sorted(AttendanceRecord.objects.filter(student=self.riya).values_list("date", "status")),
                         [(date(2026, 11, 19), "leave"), (date(2026, 11, 20), "leave")])
        with freeze_time("2026-11-21 10:00:00+05:30"):
            r = self.api(self.t_user).post("/api/attendance/records/mark/", {"section": self.s6a.pk, "date": "2026-11-21", "absent": []},
                                           content_type="application/json")
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(AttendanceRecord.objects.get(student=self.riya, date=date(2026, 11, 21)).status, "leave")
        self.assertEqual(AttendanceRecord.objects.get(student=self.other, date=date(2026, 11, 21)).status, "present")

    def test_change_request_applies_only_after_office_approves(self):
        api = self.portal(self.login(), self.branch)
        r = api.post(f"/api/portal/children/{self.riya.pk}/change/", {"field": "phone", "new_value": "98765 11111"},
                     content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        g = Guardian.objects.get(branch=self.branch, student_links__student=self.riya)
        self.assertEqual(g.phone, "+91 98765 00001")
        admin = self.api(self.make_user("admin"))
        self.assertEqual(self.api(self.t_user).get("/api/portal/change-requests/").status_code, 403)
        r = admin.post(f"/api/portal/change-requests/{r.json()['id']}/decide/", {"approve": True}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        g.refresh_from_db()
        self.assertEqual(g.phone, "9876511111")
        # Riya now follows the new number; the old number (still on Aman's record) keeps Aman only
        self.assertEqual([c["name"] for c in api.get("/api/portal/me/").json()["children"]], ["Aman Kumar"])
        new_login = self.portal(self.login("9876511111"))
        self.assertEqual([c["name"] for c in new_login.get("/api/portal/me/").json()["children"]], ["Riya Kumari"])

    def test_notice_read_receipt_visible_to_office(self):
        admin_user = self.make_user("admin")
        n = Notice.objects.create(branch=self.branch, title="PTM", body="Saturday 10 am", audience="section", section=self.s6a)
        send_notice(notice=n, by="admin")
        api = self.portal(self.login(), self.branch)
        rows = api.get(f"/api/portal/children/{self.riya.pk}/notices/").json()
        self.assertEqual([(x["title"], x["read"]) for x in rows], [("PTM", False)])
        api.post(f"/api/portal/children/{self.riya.pk}/read-notice/", {"notice": n.pk}, content_type="application/json")
        reads = self.api(admin_user).get(f"/api/notify/notices/{n.pk}/reads/").json()
        self.assertEqual(reads["read"], 1)
        self.assertEqual([r["name"] for r in reads["rows"] if r["read_at"]], ["Riya Kumari"])

"""Homework and online learning acceptance scenarios (scope doc, Learning 1–4) plus teacher scope.

    python manage.py test apps.learning.tests.test_learning

The parent-side half of LRN-1 (grade visible on the portal) is in apps.portal.tests.
"""
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from freezegun import freeze_time

from apps.core.testing import EraTestCase
from apps.learning import services
from apps.learning.models import Attempt, Homework, JoinRecord, OnlineClass, OnlineTest, Submission
from apps.notify.models import Message
from apps.people.models import Enrollment, Guardian, Program, Section, StudentGuardian, Subject, TeachingAssignment

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
TMP = tempfile.mkdtemp(prefix="eraj-learning-")


def at(s: str) -> datetime:
    return timezone.make_aware(datetime.fromisoformat(s))


@override_settings(MEDIA_ROOT=TMP)
class LearningBase(EraTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.p6 = Program.objects.create(branch=self.branch, code="C6", name="Class 6")
        self.s6a = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p6, name="A")
        self.s6b = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p6, name="B")
        self.maths = Subject.objects.create(branch=self.branch, code="C6-MAT", name="Maths", program=self.p6)
        self.hindi = Subject.objects.create(branch=self.branch, code="C6-HIN", name="Hindi", program=self.p6)
        self.t_user = self.make_user("teacher")
        self.anita = self.make_staff(user=self.t_user, full_name="Anita Maths")
        TeachingAssignment.objects.create(branch=self.branch, staff=self.anita, subject=self.maths, section=self.s6a)
        self.other_user = self.make_user("teacher")
        self.chanda = self.make_staff(user=self.other_user, full_name="Chanda Hindi")
        TeachingAssignment.objects.create(branch=self.branch, staff=self.chanda, subject=self.hindi, section=self.s6a)
        self.kids = [self.kid(self.s6a, f"98110000{i:02d}", f"Kid {i:02d}") for i in range(1, 4)]
        self.b1 = self.kid(self.s6b, "9822000001", "Kid B1")

    def kid(self, section, phone, name):
        s = self.make_student(full_name=name)
        Enrollment.objects.create(branch=self.branch, student=s, academic_year=self.year, program=section.program, section=section)
        g = Guardian.objects.create(branch=self.branch, full_name=f"Parent of {name}", phone=phone)
        StudentGuardian.objects.create(branch=self.branch, student=s, guardian=g, relation="mother", is_primary=True)
        return s

    def teacher(self):
        return self.api(self.t_user)


@freeze_time("2026-11-20 10:00:00+05:30")
class Scenario1Test(LearningBase):
    def test_scenario_learning_1_homework_with_pdf_photo_submission_graded(self):
        api = self.teacher()
        r = api.post("/api/learning/homework/", {"section": self.s6a.pk, "subject": self.maths.pk, "title": "Fractions ex 4.2",
                                                 "description": "Q1–Q10", "due_date": "2026-11-22"}, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        hw = r.json()["id"]
        self.assertEqual(r.json()["teacher_name"], "Anita Maths")
        r = api.post(f"/api/learning/homework/{hw}/attach/", {"files": SimpleUploadedFile("ex42.pdf", PDF, content_type="application/pdf")})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([f["name"] for f in r.json()["files"]], ["ex42.pdf"])
        fid = r.json()["files"][0]["id"]
        r = api.get(f"/api/learning/homework/{hw}/file/?file={fid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), PDF)
        # every parent in 6-A got the homework alert; 6-B did not
        sent = Message.objects.filter(event="learning.homework_set")
        self.assertEqual(sorted(m.student_id for m in sent.distinct("student_id").order_by("student_id")),
                         sorted(k.pk for k in self.kids))
        self.assertFalse(sent.filter(student=self.b1).exists())

        kid = self.kids[0]
        sub = services.submit(homework=Homework.objects.get(pk=hw), student=kid, text="",
                              files=[SimpleUploadedFile("page1.jpg", JPG, content_type="image/jpeg")])
        self.assertFalse(sub.late)
        r = api.get(f"/api/learning/submissions/?homework={hw}")
        self.assertEqual(r.json()["count"], 1)
        row = r.json()["results"][0]
        self.assertEqual(row["student_name"], kid.full_name)
        r = api.post(f"/api/learning/submissions/{row['id']}/grade/", {"grade": "A", "remarks": "Neat work"}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["grade"], r.json()["remarks"]), ("A", "Neat work"))
        # once checked, the student can't change it
        with self.assertRaisesMessage(Exception, "already checked"):
            services.submit(homework=Homework.objects.get(pk=hw), student=kid, text="new answer")

    def test_attachment_type_is_checked_by_content(self):
        hw = Homework.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, teacher=self.anita, title="X",
                                     due_date=date(2026, 11, 22))
        r = self.teacher().post(f"/api/learning/homework/{hw.pk}/attach/",
                                {"files": SimpleUploadedFile("x.pdf", b"<html>", content_type="application/pdf")})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(hw.files.exists())


class Scenario2Test(LearningBase):
    def test_scenario_learning_2_submission_after_due_date_is_late(self):
        hw = Homework.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, teacher=self.anita,
                                     title="Ex 4.3", due_date=date(2026, 11, 20))
        on_time = services.submit(homework=hw, student=self.kids[0], text="done", now=at("2026-11-20T23:59:00"))
        late = services.submit(homework=hw, student=self.kids[1], text="done", now=at("2026-11-21T07:30:00"))
        self.assertFalse(on_time.late)
        self.assertTrue(late.late)
        r = self.teacher().get(f"/api/learning/submissions/?homework={hw.pk}&late=true")
        self.assertEqual([x["student"] for x in r.json()["results"]], [self.kids[1].pk])
        # another section's student can't submit
        with self.assertRaisesMessage(Exception, "another section"):
            services.submit(homework=hw, student=self.b1, text="x")


@freeze_time("2026-11-20 10:00:00+05:30")
class Scenario3Test(LearningBase):
    def test_scenario_learning_3_online_class_in_timetable_and_join_record(self):
        api = self.teacher()
        r = api.post("/api/learning/classes/", {"section": self.s6a.pk, "subject": self.maths.pk, "title": "Revision",
                                                "starts_at": "2026-11-20T15:00:00+05:30", "ends_at": "2026-11-20T15:40:00+05:30",
                                                "link": "https://meet.google.com/abc-defg-hij"}, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.json()["id"]
        resp = api.get(f"/api/timetable/views/section/?section={self.s6a.pk}&date=2026-11-20")
        self.assertEqual(resp.status_code, 200, resp.content)
        grid = resp.json()
        self.assertEqual([(o["id"], o["title"]) for o in grid["online"]], [(cid, "Revision")])
        other_day = api.get(f"/api/timetable/views/section/?section={self.s6a.pk}&date=2026-11-21").json()
        self.assertEqual(other_day["online"], [])

        c = OnlineClass.objects.get(pk=cid)
        with self.assertRaisesMessage(Exception, "opens at 15:00"):
            services.join(online_class=c, student=self.kids[0], now=at("2026-11-20T14:30:00"))
        self.assertEqual(services.join(online_class=c, student=self.kids[0], now=at("2026-11-20T14:50:00")), c.link)
        services.join(online_class=c, student=self.kids[0], now=at("2026-11-20T15:05:00"))
        services.join(online_class=c, student=self.kids[1], now=at("2026-11-20T15:10:00"))
        with self.assertRaisesMessage(Exception, "ended"):
            services.join(online_class=c, student=self.kids[2], now=at("2026-11-20T15:41:00"))
        r = api.get(f"/api/learning/classes/{cid}/joins/").json()
        self.assertEqual((r["joined"], r["of"]), (2, 3))
        opened = {row["name"]: row["opens"] for row in r["rows"]}
        self.assertEqual(opened, {"Kid 01": 2, "Kid 02": 1, "Kid 03": 0})
        self.assertEqual(JoinRecord.objects.count(), 2)

    def test_class_ending_before_it_starts_is_refused(self):
        r = self.teacher().post("/api/learning/classes/", {"section": self.s6a.pk, "subject": self.maths.pk, "title": "X",
                                                           "starts_at": "2026-11-20T15:00:00+05:30", "ends_at": "2026-11-20T14:00:00+05:30",
                                                           "link": "https://meet.google.com/x"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)


class Scenario4Test(LearningBase):
    def make_test(self):
        questions = [{"sequence": i + 1, "text": f"{i + 1} + 1 = ?", "options": [str(i + 1), str(i + 2), str(i + 3)], "correct": 1}
                     for i in range(10)]
        r = self.teacher().post("/api/learning/tests/", {
            "section": self.s6a.pk, "subject": self.maths.pk, "title": "Addition quiz", "opens_at": "2026-11-20T09:00:00+05:30",
            "closes_at": "2026-11-20T17:00:00+05:30", "time_limit_minutes": 15, "published": True, "questions": questions,
        }, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["question_count"], 10)
        return OnlineTest.objects.get(pk=r.json()["id"])

    def test_scenario_learning_4_ten_question_test_scored_automatically(self):
        t = self.make_test()
        qs = list(t.questions.order_by("sequence"))
        k1, k2, k3 = self.kids
        a1 = services.start_attempt(test=t, student=k1, now=at("2026-11-20T10:00:00"))
        services.submit_attempt(attempt=a1, answers={str(q.pk): 1 for q in qs}, now=at("2026-11-20T10:08:00"))          # 10/10
        a2 = services.start_attempt(test=t, student=k2, now=at("2026-11-20T10:00:00"))
        services.submit_attempt(attempt=a2, answers={str(q.pk): (1 if i < 6 else 0) for i, q in enumerate(qs)},
                                now=at("2026-11-20T10:12:00"))                                                         # 6/10
        a3 = services.start_attempt(test=t, student=k3, now=at("2026-11-20T10:00:00"))
        a3.answers = {str(qs[0].pk): 1, str(qs[1].pk): 1, str(qs[2].pk): 2}                                            # saved, never submitted
        a3.save(update_fields=["answers"])
        self.assertEqual(a3.deadline, at("2026-11-20T10:15:00"))
        with freeze_time("2026-11-20 11:00:00+05:30"):
            r = self.teacher().get(f"/api/learning/tests/{t.pk}/results/")
        self.assertEqual(r.status_code, 200)
        rows = {row["name"]: row for row in r.json()["rows"]}
        self.assertEqual({n: (Decimal(str(x["score"])), x["status"]) for n, x in rows.items()},
                         {"Kid 01": (Decimal(10), "submitted"), "Kid 02": (Decimal(6), "submitted"), "Kid 03": (Decimal(2), "submitted")})
        self.assertTrue(rows["Kid 03"]["auto_submitted"])
        self.assertEqual(Decimal(str(r.json()["average"])), Decimal("6.00"))

    def test_answers_after_time_limit_are_flagged_and_bad_answers_ignored(self):
        t = self.make_test()
        q = t.questions.first()
        a = services.start_attempt(test=t, student=self.kids[0], now=at("2026-11-20T16:50:00"))
        self.assertEqual(a.deadline, at("2026-11-20T17:00:00"))                     # capped at closing time
        a = services.submit_attempt(attempt=a, answers={str(q.pk): 1, "999999": 1, str(q.pk + 1): "drop table"},
                                    now=at("2026-11-20T17:05:00"))
        self.assertTrue(a.auto_submitted)
        self.assertEqual(a.score, Decimal(1))
        self.assertEqual(list(a.answers), [str(q.pk)])
        with self.assertRaisesMessage(Exception, "Already submitted"):
            services.submit_attempt(attempt=a, answers={}, now=at("2026-11-20T17:06:00"))
        with self.assertRaisesMessage(Exception, "another section"):
            services.start_attempt(test=t, student=self.b1, now=at("2026-11-20T10:00:00"))

    def test_questions_locked_once_a_student_starts(self):
        t = self.make_test()
        services.start_attempt(test=t, student=self.kids[0], now=at("2026-11-20T10:00:00"))
        r = self.teacher().patch(f"/api/learning/tests/{t.pk}/", {"questions": []}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Attempt.objects.count(), 1)


@freeze_time("2026-11-20 10:00:00+05:30")
class TeacherScopeTest(LearningBase):
    def test_teacher_sees_and_sets_only_own_section_and_subject(self):
        Homework.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, teacher=self.anita, title="Maths hw",
                                due_date=date(2026, 11, 22))
        Homework.objects.create(branch=self.branch, section=self.s6a, subject=self.hindi, teacher=self.chanda, title="Hindi hw",
                                due_date=date(2026, 11, 22))
        titles = [h["title"] for h in self.teacher().get("/api/learning/homework/").json()["results"]]
        self.assertEqual(titles, ["Maths hw"])
        r = self.teacher().post("/api/learning/homework/", {"section": self.s6b.pk, "subject": self.maths.pk, "title": "x",
                                                            "due_date": "2026-11-22"}, content_type="application/json")
        self.assertEqual(r.status_code, 409)
        hindi = Homework.objects.get(title="Hindi hw")
        self.assertEqual(self.teacher().get(f"/api/learning/homework/{hindi.pk}/").status_code, 404)
        sub = services.submit(homework=hindi, student=self.kids[0], text="x")
        self.assertEqual(self.teacher().post(f"/api/learning/submissions/{sub.pk}/grade/", {"grade": "B"},
                                             content_type="application/json").status_code, 404)
        # Admin sees every section
        admin = self.api(self.make_user("admin"))
        self.assertEqual(admin.get("/api/learning/homework/").json()["count"], 2)

    def test_reports_submission_rate_pending_and_scores(self):
        hw = Homework.objects.create(branch=self.branch, section=self.s6a, subject=self.maths, teacher=self.anita, title="Ex 1",
                                     due_date=date(2026, 11, 18))
        services.submit(homework=hw, student=self.kids[0], text="a", now=at("2026-11-18T10:00:00"))
        services.submit(homework=hw, student=self.kids[1], text="b", now=at("2026-11-19T10:00:00"))
        admin = self.api(self.make_user("admin"))
        rates = admin.get("/api/learning/reports/submissions/?from=2026-11-01&to=2026-11-30").json()
        self.assertEqual([(r["section"], r["homework"], r["expected"], r["submitted"], r["late"], r["rate"]) for r in rates],
                         [(str(self.s6a), 1, 3, 2, 1, 67)])
        by_student = admin.get(f"/api/learning/reports/submissions/?from=2026-11-01&to=2026-11-30&section={self.s6a.pk}&by=student").json()
        self.assertEqual({r["name"]: r["submitted"] for r in by_student}, {"Kid 01": 1, "Kid 02": 1, "Kid 03": 0})
        pending = admin.get("/api/learning/reports/pending/").json()
        self.assertEqual([(p["homework"], p["missing"], p["students"]) for p in pending], [(hw.pk, 1, "Kid 03")])
        self.assertEqual(admin.get("/api/learning/reports/tests/").status_code, 200)
        self.assertEqual(Submission.objects.count(), 2)

"""HR acceptance scenarios (scope doc, HR 1–4) and guards. Real tenant schema.

    python manage.py test apps.hr.tests.test_hr
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from freezegun import freeze_time

from apps.attendance.models import AttendanceCard, Holiday
from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.hr import services
from apps.hr.models import LeaveApplication, LeaveBalance, LeaveType, StaffAttendance, StaffDocument
from apps.people.models import Department

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
TODAY = date(2026, 11, 20)  # a Friday; Sundays are the weekly off


def j(r):
    return r.json() if r.get("Content-Type", "").startswith("application/json") else r.content


@freeze_time("2026-11-20 10:00:00+05:30")
class HRBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.dept = Department.objects.create(branch=self.branch, name="Science")
        self.cl = LeaveType.objects.create(branch=self.branch, code="CL", name="Casual leave", annual_days=Decimal("8"))
        self.lwp = LeaveType.objects.create(branch=self.branch, code="LWP", name="Leave without pay", annual_days=None, paid=False)
        self.hr = self.api(self.make_user("hr"))
        self.admin = self.api(self.make_user("admin"))

    def post(self, client, url, body):
        return client.post(url, body, content_type="application/json")

    def set_cl(self, staff, entitled):
        b = services.balance_for(staff=staff, leave_type=self.cl, year=2026)
        b.entitled = Decimal(entitled)
        b.save()
        return b


class Scenario1Test(HRBase):
    def test_scenario_hr_1_staff_with_documents_is_eligible_in_library(self):
        r = self.post(self.hr, "/api/people/staff/", {"employee_code": "T-101", "full_name": "Rekha Kumari",
                                                       "designation": "TGT", "department": self.dept.pk,
                                                       "date_joined": "2026-04-01"})
        self.assertEqual(r.status_code, 201, r.content)
        staff_id = r.json()["id"]
        r = self.post(self.hr, "/api/hr/profiles/", {"staff": staff_id, "pan": "abcde1234f", "uan": "100200300400",
                                                      "bank_account": "123456789012", "ifsc": "sbin0001234"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["pan"], "ABCDE1234F")
        up = SimpleUploadedFile("appointment.pdf", PDF, content_type="application/pdf")
        r = self.hr.post("/api/hr/documents/", {"staff": staff_id, "kind": "appointment", "title": "Appointment letter", "file": up})
        self.assertEqual(r.status_code, 201, r.content)
        doc = StaffDocument.objects.get(pk=r.json()["id"])
        self.assertNotIn("appointment", doc.file.name)  # stored under a random name
        dl = self.hr.get(r.json()["download_url"])
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(b"".join(dl.streaming_content), PDF)
        # Library: the new staff member can be made a borrower
        lib = self.api(self.make_user("librarian"))
        self.assertIn(staff_id, [s["id"] for s in lib.get("/api/people/staff/?search=Rekha").json()["results"]])
        r = self.post(lib, "/api/library/members/", {"staff": staff_id})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["member_type"], "staff")
        # Inventory reads the same registry list (issue-to-staff arrives with M5)
        store = self.api(self.make_user("store"))
        self.assertIn(staff_id, [s["id"] for s in store.get("/api/people/staff/").json()["results"]])

    def test_documents_reject_wrong_type_size_and_spoofed_content(self):
        s = self.make_staff()
        bad = SimpleUploadedFile("x.exe", b"MZ....", content_type="application/octet-stream")
        self.assertEqual(self.hr.post("/api/hr/documents/", {"staff": s.pk, "title": "x", "file": bad}).status_code, 400)
        fake = SimpleUploadedFile("x.pdf", b"<html>not a pdf", content_type="application/pdf")
        r = self.hr.post("/api/hr/documents/", {"staff": s.pk, "title": "x", "file": fake})
        self.assertEqual(r.status_code, 400)
        self.assertIn("don't match", str(r.json()))
        big = SimpleUploadedFile("big.pdf", PDF + b"0" * (5 * 1024 * 1024), content_type="application/pdf")
        self.assertEqual(self.hr.post("/api/hr/documents/", {"staff": s.pk, "title": "x", "file": big}).status_code, 400)

    def test_profile_identity_hidden_from_teachers_and_masked_in_lists(self):
        s = self.make_staff()
        self.post(self.hr, "/api/hr/profiles/", {"staff": s.pk, "bank_account": "998877665544"})
        self.assertEqual(self.api(self.make_user("teacher")).get("/api/hr/profiles/").status_code, 403)
        row = self.api(self.make_user("accountant")).get("/api/hr/profiles/").json()["results"][0]
        self.assertEqual(row["bank_account"], "••••••••5544")
        detail = self.hr.get(f"/api/hr/profiles/{row['id']}/").json()
        self.assertEqual(detail["bank_account"], "998877665544")
        self.assertEqual(self.api(self.make_user("accountant")).post(
            "/api/hr/profiles/", {"staff": self.make_staff().pk}, content_type="application/json").status_code, 403)


class Scenario2Test(HRBase):
    def test_scenario_hr_2_three_days_casual_leave_against_two_is_refused(self):
        s = self.make_staff()
        self.set_cl(s, 2)
        r = self.post(self.hr, "/api/hr/leave/", {"staff": s.pk, "leave_type": self.cl.pk, "start": "2026-11-23", "end": "2026-11-25"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Only 2 day(s) of CL left", r.json()["detail"])
        self.assertFalse(LeaveApplication.objects.exists())

    def test_pending_applications_reserve_balance(self):
        s = self.make_staff()
        self.set_cl(s, 2)
        services.apply_leave(staff=s, leave_type=self.cl, start=date(2026, 11, 23), end=date(2026, 11, 24), by="t")
        with self.assertRaisesMessage(Conflict, "Only 0 day(s)"):
            services.apply_leave(staff=s, leave_type=self.cl, start=date(2026, 11, 26), end=date(2026, 11, 26), by="t")

    def test_weekly_offs_and_holidays_are_not_counted_and_overlaps_refused(self):
        s = self.make_staff()
        Holiday.objects.create(branch=self.branch, date=date(2026, 11, 24), name="Chhath")
        app = services.apply_leave(staff=s, leave_type=self.cl, start=date(2026, 11, 21), end=date(2026, 11, 25), by="t")
        self.assertEqual(app.days, Decimal("3"))  # Sat, Mon, Wed — Sun off, Tue holiday
        with self.assertRaisesMessage(Conflict, "Overlaps CL leave"):
            services.apply_leave(staff=s, leave_type=self.lwp, start=date(2026, 11, 25), end=date(2026, 11, 26), by="t")


class Scenario3Test(HRBase):
    def test_scenario_hr_3_approved_two_days_update_balance_and_register(self):
        s = self.make_staff(department=self.dept)
        self.set_cl(s, 8)
        r = self.post(self.hr, "/api/hr/leave/", {"staff": s.pk, "leave_type": self.cl.pk, "start": "2026-11-16",
                                                   "end": "2026-11-17", "reason": "Family function"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["days"], "2.0")
        app_id = r.json()["id"]
        self.assertEqual(self.post(self.api(self.make_user("accountant")), f"/api/hr/leave/{app_id}/approve/", {}).status_code, 403)
        r = self.post(self.hr, f"/api/hr/leave/{app_id}/approve/", {"remarks": "OK"})
        self.assertEqual(r.status_code, 200, r.content)
        bal = LeaveBalance.objects.get(staff=s, leave_type=self.cl, year=2026)
        self.assertEqual((bal.entitled, bal.used), (Decimal("8"), Decimal("2")))
        reg = self.hr.get("/api/hr/attendance/register/?month=2026-11").json()
        row = next(x for x in reg["rows"] if x["staff"] == s.pk)
        self.assertEqual(row["marks"][15:17], ["CL", "CL"])  # 16th and 17th
        self.assertEqual(row["leave"], 2)
        self.assertEqual(row["lop_days"], 0)
        pdf = self.hr.get("/api/hr/attendance/register/?month=2026-11&pdf=1")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        # the timetable substitution list sees the leave
        from apps.timetable.services import absent_on

        self.assertIn(s.pk, absent_on(self.branch, date(2026, 11, 16)))
        # cancelling the approved leave gives the days back
        r = self.post(self.hr, f"/api/hr/leave/{app_id}/cancel/", {})
        self.assertEqual(r.status_code, 200, r.content)
        bal.refresh_from_db()
        self.assertEqual(bal.used, Decimal("0"))
        self.assertFalse(StaffAttendance.objects.filter(staff=s).exists())

    def test_unpaid_leave_counts_as_loss_of_pay_and_rejection_needs_reason(self):
        s = self.make_staff()
        app = services.apply_leave(staff=s, leave_type=self.lwp, start=date(2026, 11, 2), end=date(2026, 11, 3), by="t")
        with self.assertRaisesMessage(Conflict, "reason"):
            services.reject_leave(application=app, by="hr")
        services.approve_leave(application=app, by="hr")
        self.assertEqual(services.lop_days(staff=s, start=date(2026, 11, 1), end=date(2026, 11, 30)), Decimal("2"))

    def test_staff_self_service_sees_and_applies_only_for_self(self):
        teacher_user = self.make_user("teacher")
        me = self.make_staff(user=teacher_user)
        other = self.make_staff()
        self.set_cl(me, 4)
        api = self.api(teacher_user)
        r = self.post(api, "/api/hr/me/apply/", {"leave_type": self.cl.pk, "start": "2026-11-23", "end": "2026-11-23"})
        self.assertEqual(r.status_code, 201, r.content)
        summary = api.get("/api/hr/me/summary/").json()
        self.assertEqual(summary["staff"], me.pk)
        self.assertEqual(next(b for b in summary["balances"] if b["leave_type_code"] == "CL")["available"], "3.0")
        other_app = services.apply_leave(staff=other, leave_type=self.cl, start=date(2026, 11, 23), end=date(2026, 11, 23), by="x")
        self.assertEqual(self.post(api, f"/api/hr/me/{other_app.pk}/cancel/", {}).status_code, 404)
        self.assertEqual(api.get("/api/hr/leave/").status_code, 403)
        self.assertEqual(self.post(api, f"/api/hr/me/{r.json()['id']}/cancel/", {}).status_code, 200)


class Scenario4Test(HRBase):
    def test_scenario_hr_4_left_staff_vanish_from_active_lists_and_stay_in_history(self):
        s = self.make_staff(full_name="Mohan Lal")
        pending = services.apply_leave(staff=s, leave_type=self.cl, start=date(2026, 11, 23), end=date(2026, 11, 23), by="t")
        r = self.post(self.hr, f"/api/hr/staff/{s.pk}/exit/", {"relieved_on": "2026-11-20", "reason": "Resigned"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "left")
        ids = lambda url: [x["id"] for x in self.hr.get(url).json()["results"]]  # noqa: E731
        self.assertNotIn(s.pk, ids("/api/people/staff/"))
        self.assertNotIn(s.pk, ids("/api/hr/staff/"))
        self.assertIn(s.pk, ids("/api/people/staff/?status=left"))
        self.assertIn(s.pk, ids("/api/hr/staff/?status=all"))
        self.assertEqual(self.hr.get(f"/api/people/staff/{s.pk}/").json()["full_name"], "Mohan Lal")
        pending.refresh_from_db()
        self.assertEqual(pending.status, "cancelled")
        self.assertNotIn(s.pk, [x["staff"] for x in self.hr.get("/api/hr/attendance/day/").json()["rows"]])
        self.assertEqual(self.post(self.hr, f"/api/hr/staff/{s.pk}/exit/", {"relieved_on": "2026-11-20", "reason": "x"}).status_code, 409)
        with self.assertRaisesMessage(Conflict, "has left"):
            services.apply_leave(staff=s, leave_type=self.cl, start=date(2026, 11, 24), end=date(2026, 11, 24), by="t")


class StaffAttendanceTest(HRBase):
    def test_one_save_marks_everyone_and_past_corrections_are_admin_only(self):
        a, b, c = self.make_staff(), self.make_staff(), self.make_staff()
        r = self.post(self.hr, "/api/hr/attendance/mark/", {"date": "2026-11-20", "absent": [b.pk], "statuses": {str(c.pk): "on_duty"}})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["created"], 3)
        got = dict(StaffAttendance.objects.filter(date=TODAY).values_list("staff_id", "status"))
        self.assertEqual(got, {a.pk: "present", b.pk: "absent", c.pk: "on_duty"})
        self.post(self.hr, "/api/hr/attendance/mark/", {"date": "2026-11-19"})
        r = self.post(self.hr, "/api/hr/attendance/mark/", {"date": "2026-11-19", "absent": [a.pk]})
        self.assertEqual(r.status_code, 409)
        r = self.post(self.admin, "/api/hr/attendance/mark/", {"date": "2026-11-19", "absent": [a.pk]})
        self.assertEqual(r.json()["updated"], 1)
        self.assertEqual(self.post(self.hr, "/api/hr/attendance/mark/", {"date": "2026-11-22"}).status_code, 409)  # Sunday
        self.assertEqual(self.post(self.hr, "/api/hr/attendance/mark/", {"date": "2026-11-21", "statuses": {str(a.pk): "leave"}}).status_code, 400)
        absentees = self.hr.get("/api/hr/reports/absentees/?date=2026-11-20").json()
        self.assertEqual([x["staff"] for x in absentees["away"]], [b.pk])

    def test_staff_punch_marks_present_once(self):
        s = self.make_staff()
        AttendanceCard.objects.create(branch=self.branch, code="E77", staff=s)
        from apps.attendance.services import ingest_punch

        at = timezone.make_aware(datetime(2026, 11, 20, 8, 55))
        ingest_punch(branch=self.branch, code="E77", at=at, device=None, source="import")
        ingest_punch(branch=self.branch, code="E77", at=at + timedelta(hours=8), device=None, source="import")
        row = StaffAttendance.objects.get(staff=s)
        self.assertEqual((row.date, row.status, row.source), (TODAY, "present", "device"))

    def test_other_branch_is_invisible(self):
        other = self.make_branch("east")
        s = self.make_staff(branch=other)
        services.apply_leave(staff=s, leave_type=LeaveType.objects.create(branch=other, code="CL", name="CL", annual_days=5),
                             start=date(2026, 11, 23), end=date(2026, 11, 23), by="x")
        self.assertEqual(self.hr.get("/api/hr/leave/").json()["count"], 0)
        r = self.post(self.hr, "/api/hr/leave/", {"staff": s.pk, "leave_type": self.cl.pk, "start": "2026-11-23", "end": "2026-11-23"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post(self.hr, f"/api/hr/staff/{s.pk}/exit/", {"relieved_on": "2026-11-20", "reason": "x"}).status_code, 404)

    def test_reports_headcount_and_balances(self):
        self.make_staff(department=self.dept)
        self.make_staff(department=self.dept, employment_type="contract")
        hc = self.hr.get("/api/hr/reports/headcount/").json()
        self.assertEqual(hc, [{"department": "Science", "permanent": 1, "contract": 1, "part_time": 0, "total": 2}])
        n = self.post(self.hr, "/api/hr/balances/open-year/", {"year": 2026}).json()["created"]
        self.assertEqual(n, 2)
        rows = self.hr.get("/api/hr/reports/balances/?year=2026").json()
        self.assertEqual({r["available"] for r in rows}, {8})
        xlsx = self.hr.get("/api/hr/reports/balances/?year=2026&format=xlsx")
        self.assertEqual(xlsx.status_code, 200)
        from openpyxl import load_workbook

        self.assertEqual(load_workbook(BytesIO(xlsx.content)).active.max_row, 3)

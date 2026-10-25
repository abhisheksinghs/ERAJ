"""Visitors and outpass acceptance scenarios. Real tenant schema.

    python manage.py test apps.hostel.tests.test_gate
"""
from datetime import date
from unittest import mock

from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.hostel import gate, mess
from apps.hostel.models import ApprovedVisitor, Mess, MessLeave, Outpass, Visit
from apps.people.models import Guardian, StudentGuardian


class GateBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.student = self.make_student()
        g = Guardian.objects.create(branch=self.branch, full_name="Father", phone="9800011111")
        StudentGuardian.objects.create(branch=self.branch, student=self.student, guardian=g, relation="father", is_primary=True)


class VisitorTest(GateBase):
    def test_unlisted_visitor_held_until_warden_approves_and_times_logged(self):
        ApprovedVisitor.objects.create(branch=self.branch, student=self.student, name="Father", relation="father", phone="9800011111")
        known = gate.visitor_arrives(student=self.student, name="", phone="9800011111")
        self.assertEqual((known.status, known.name), (Visit.Status.IN, "Father"))

        warden = self.api(self.make_user("warden"))
        r = warden.post("/api/hostel/visits/", {"student": self.student.pk, "name": "Cousin", "relation": "cousin",
                                                "id_proof": "DL-1234"}, content_type="application/json")
        self.assertEqual(r.json()["status"], "held")
        self.assertIsNone(r.json()["time_in"])
        vid = r.json()["id"]
        r = warden.post(f"/api/hostel/visits/{vid}/approve/")
        self.assertEqual(r.json()["status"], "in")
        r = warden.post(f"/api/hostel/visits/{vid}/leave/")
        self.assertEqual(r.json()["status"], "out")
        self.assertIsNotNone(r.json()["time_in"])
        self.assertIsNotNone(r.json()["time_out"])

    def test_accountant_cannot_approve_visitors(self):
        v = gate.visitor_arrives(student=self.student, name="Stranger")
        r = self.api(self.make_user("accountant")).post(f"/api/hostel/visits/{v.pk}/approve/")
        self.assertEqual(r.status_code, 403)


class OutpassTest(GateBase):
    def setUp(self):
        super().setUp()
        self.mess = Mess.objects.create(branch=self.branch, name="Central", monthly_charge=3000, rebate_min_days=5,
                                        rebate_per_day=90)
        self.member = mess.enrol(mess=self.mess, student=self.student, start=date(2026, 10, 1))

    @mock.patch("apps.core.notify.log")
    def test_seven_day_outpass_alerts_parent_and_counts_as_mess_leave(self, log):
        with freeze_time("2026-10-08T10:00:00+05:30"):
            op = gate.request_outpass(student=self.student, from_date=date(2026, 10, 10), to_date=date(2026, 10, 16),
                                      reason="Chhath puja", requested_by="parent")
            gate.decide_outpass(outpass=op, approve=True, by="warden@x")
        leave = MessLeave.objects.get(outpass=op)
        self.assertEqual((leave.from_date, leave.to_date, leave.days), (date(2026, 10, 10), date(2026, 10, 16), 7))
        with freeze_time("2026-10-10T07:00:00+05:30"):
            gate.gate_out(outpass=op)
        with freeze_time("2026-10-16T17:00:00+05:30"):
            op = gate.gate_in(outpass=op)
        self.assertFalse(op.is_late)
        events = [c.args[2] for c in log.info.call_args_list]
        self.assertEqual(events, ["outpass.requested", "outpass.approved", "outpass.out", "outpass.returned"])
        self.assertTrue(all(c.args[3] == "9800011111" for c in log.info.call_args_list))

        with freeze_time("2026-11-01"):
            mess.bill_mess_month(branch=self.branch)
        from apps.hostel.models import MessRebate
        self.assertEqual(MessRebate.objects.get().days, 7)

    def test_late_return_flagged_and_early_return_shortens_leave(self):
        with freeze_time("2026-10-08"):
            op = gate.request_outpass(student=self.student, from_date=date(2026, 10, 10), to_date=date(2026, 10, 12), reason="Home")
            gate.decide_outpass(outpass=op, approve=True, by="w")
            gate.gate_out(outpass=op)
        with freeze_time("2026-10-12T21:30:00+05:30"):  # after the 18:00 default
            self.assertTrue(gate.gate_in(outpass=op).is_late)

        with freeze_time("2026-10-20"):
            op2 = gate.request_outpass(student=self.student, from_date=date(2026, 10, 21), to_date=date(2026, 10, 30), reason="Home")
            gate.decide_outpass(outpass=op2, approve=True, by="w")
            gate.gate_out(outpass=op2)
        with freeze_time("2026-10-25T12:00:00+05:30"):
            gate.gate_in(outpass=op2)
        self.assertEqual(MessLeave.objects.get(outpass=op2).to_date, date(2026, 10, 25))

    def test_rejected_outpass_cannot_leave_and_overlap_refused(self):
        op = gate.request_outpass(student=self.student, from_date=date(2026, 10, 10), to_date=date(2026, 10, 12), reason="x")
        with self.assertRaises(Conflict):
            gate.request_outpass(student=self.student, from_date=date(2026, 10, 11), to_date=date(2026, 10, 13), reason="y")
        gate.decide_outpass(outpass=op, approve=False, by="w")
        self.assertEqual(op.__class__.objects.get(pk=op.pk).status, Outpass.Status.REJECTED)
        with self.assertRaises(Conflict):
            gate.gate_out(outpass=op)
        self.assertFalse(MessLeave.objects.exists())

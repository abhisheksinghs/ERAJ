"""
Fees acceptance scenarios (client scope document, Fees 1–7) plus money edge
cases. Real tenant schema.

    python manage.py test apps.fees
"""
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.exceptions import Conflict
from apps.core.numwords import rupees_in_words
from apps.core.testing import EraTestCase
from apps.fees import services
from apps.fees.models import Charge, Concession, FeeHead, FeePlan, FeePlanInstalment, Receipt
from apps.fees.selectors import charges_with_balance, students_with_dues
from apps.org.models import Role
from apps.people.models import Enrollment, Guardian, Program, Section, Student, StudentGuardian

D = Decimal


class FeesBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.program = Program.objects.create(branch=self.branch, code="C6", name="Class 6")
        self.section = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.program, name="A")
        self.tuition = FeeHead.objects.create(branch=self.branch, code="TUI", name="Tuition", kind="tuition")
        self.plan = FeePlan.objects.create(
            branch=self.branch, name="Class 6 tuition", academic_year=self.year, program=self.program, head=self.tuition
        )
        for i, d in enumerate([date(2026, 4, 10), date(2026, 7, 10), date(2026, 10, 10), date(2027, 1, 10)], start=1):
            FeePlanInstalment.objects.create(plan=self.plan, sequence=i, label=f"Q{i}", due_date=d, amount=D("3000"))
        self.accountant = self.make_user(Role.ACCOUNTANT)
        self.admin = self.make_user(Role.ADMIN)

    def enroll(self, student=None):
        student = student or self.make_student()
        Enrollment.objects.create(
            branch=self.branch, student=student, academic_year=self.year, program=self.program, section=self.section
        )
        return student

    def dues(self, student) -> Decimal:
        return sum((c.outstanding for c in charges_with_balance(Charge.objects.filter(student=student))), D("0"))


class FeesScenarioTest(FeesBase):
    def test_scenario_1_new_student_shows_all_four_instalments(self):
        student = self.enroll()
        charges = Charge.objects.filter(student=student).order_by("due_date")
        self.assertEqual([c.amount for c in charges], [D("3000.00")] * 4)
        self.assertEqual(self.dues(student), D("12000.00"))

    def test_plan_apply_is_idempotent(self):
        student = self.enroll()
        self.assertEqual(services.apply_plan(self.plan), 0)
        self.assertEqual(Charge.objects.filter(student=student).count(), 4)

    def test_scenario_2_concession_halves_dues_only_after_approval(self):
        student = self.enroll()
        r = self.api(self.accountant).post(
            "/api/fees/concessions/",
            {"student": student.pk, "head": self.tuition.pk, "academic_year": self.year.pk,
             "kind": "percent", "value": "50", "reason": "sibling"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.dues(student), D("12000.00"))  # still pending
        url = f"/api/fees/concessions/{r.json()['id']}/approve/"
        self.assertEqual(self.api(self.accountant).post(url).status_code, 403)  # accountant cannot approve
        self.assertEqual(self.api(self.admin).post(url).status_code, 200)
        self.assertEqual(self.dues(student), D("6000.00"))

    def test_scenario_3_part_payment_by_upi_prints_receipt_and_leaves_correct_due(self):
        student = self.enroll()
        first = Charge.objects.filter(student=student).order_by("due_date").first()
        api = self.api(self.accountant)
        no_ref = api.post(
            "/api/fees/receipts/", {"student": student.pk, "mode": "upi", "amount": "1000"}, content_type="application/json"
        )
        self.assertEqual(no_ref.status_code, 409)  # non-cash needs a reference
        r = api.post(
            "/api/fees/receipts/",
            {"student": student.pk, "mode": "upi", "reference": "UTR123", "lines": [{"charge": first.pk, "amount": "1000"}]},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["number"].endswith("/00001"))
        self.assertEqual(self.dues(student), D("11000.00"))
        pdf = api.get(f"/api/fees/receipts/{r.json()['id']}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(Receipt.objects.get(pk=r.json()["id"]).print_count, 1)

    def test_scenario_4_late_fine_after_grace_period(self):
        self.tuition.late_fine_mode = FeeHead.LateFine.PER_DAY
        self.tuition.late_fine_amount = D("10")
        self.tuition.grace_days = 5
        self.tuition.save()
        student = self.enroll()
        q1_due = date(2026, 4, 10)
        self.assertEqual(services.apply_late_fines(branch=self.branch, as_of=q1_due + timedelta(days=5)), 0)  # within grace
        services.apply_late_fines(branch=self.branch, as_of=q1_due + timedelta(days=8))  # 3 days past grace
        fine = Charge.objects.get(student=student, source_type="late_fine", parent__due_date=q1_due)
        self.assertEqual(fine.amount, D("30.00"))
        services.apply_late_fines(branch=self.branch, as_of=q1_due + timedelta(days=10))  # grows, not duplicated
        fine.refresh_from_db()
        self.assertEqual(fine.amount, D("50.00"))
        self.assertEqual(Charge.objects.filter(source_type="late_fine", parent__due_date=q1_due).count(), 1)

    def test_scenario_5_only_admin_cancels_receipts_and_reports_reflect_it(self):
        student = self.enroll()
        receipt = services.collect(student=student, mode="cash", amount=D("3000"), received_by="acc")
        url = f"/api/fees/receipts/{receipt.pk}/cancel/"
        self.assertEqual(self.api(self.accountant).post(url, {"reason": "wrong student"}, content_type="application/json").status_code, 403)
        self.assertEqual(self.api(self.admin).post(url, {"reason": ""}, content_type="application/json").status_code, 400)
        r = self.api(self.admin).post(url, {"reason": "wrong student"}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.dues(student), D("12000.00"))
        report = self.api(self.accountant).get(f"/api/fees/reports/collection/?from={receipt.date}&to={receipt.date}").json()
        self.assertEqual(Decimal(str(report["total"])), D("0"))
        self.assertEqual(report["cancelled"][0]["number"], receipt.number)
        # numbers never reused: the next receipt is 00002
        nxt = services.collect(student=student, mode="cash", amount=D("100"), received_by="acc")
        self.assertTrue(nxt.number.endswith("/00002"))

    def test_scenario_6_defaulters_list_with_guardian_phone_exports_to_excel(self):
        late = self.enroll()
        guardian = Guardian.objects.create(branch=self.branch, full_name="Mohan", phone="9800000001")
        StudentGuardian.objects.create(branch=self.branch, student=late, guardian=guardian, is_primary=True)
        paid_up = self.enroll()
        today = timezone.localdate()
        overdue_total = sum(
            (c.amount for c in Charge.objects.filter(student=paid_up, due_date__lt=today)), D("0")
        )
        if overdue_total:
            services.collect(student=paid_up, mode="cash", amount=overdue_total, received_by="acc")
        api = self.api(self.accountant)
        rows = api.get(f"/api/fees/accounts/?overdue=true&section={self.section.pk}").json()["results"]
        ids = [r["id"] for r in rows]
        if today > date(2026, 4, 10):
            self.assertIn(late.pk, ids)
            self.assertNotIn(paid_up.pk, ids)
            self.assertEqual(next(r for r in rows if r["id"] == late.pk)["guardian_phone"], "9800000001")
        xlsx = api.get(f"/api/fees/accounts/?overdue=true&section={self.section.pk}&format=xlsx")
        self.assertEqual(xlsx.status_code, 200)
        self.assertTrue(xlsx.content.startswith(b"PK"))  # xlsx is a zip
        self.assertIn("attachment", xlsx["Content-Disposition"])

    def test_scenario_7_tally_export_has_one_voucher_per_live_receipt(self):
        student = self.enroll()
        r1 = services.collect(student=student, mode="cash", amount=D("1000"), received_by="acc")
        r2 = services.collect(student=student, mode="upi", reference="UTR9", amount=D("500"), received_by="acc")
        services.cancel_receipt(receipt=r2, by="admin", reason="test")
        resp = self.api(self.accountant).get(f"/api/fees/reports/tally/?from={r1.date}&to={r1.date}")
        self.assertEqual(resp.status_code, 200)
        xml = resp.content.decode()
        self.assertEqual(xml.count('VCHTYPE="Receipt"'), 1)
        self.assertIn(r1.number, xml)
        self.assertIn("<LEDGERNAME>Cash</LEDGERNAME>", xml)
        self.assertIn("<LEDGERNAME>Tuition</LEDGERNAME>", xml)
        self.assertIn("<AMOUNT>-1000.00</AMOUNT>", xml)  # debit to cash
        self.assertIn("<AMOUNT>1000.00</AMOUNT>", xml)  # credit to tuition


class FeesRulesTest(FeesBase):
    def test_auto_allocation_pays_oldest_dues_first(self):
        student = self.enroll()
        services.collect(student=student, mode="cash", amount=D("4500"), received_by="acc")
        balances = list(charges_with_balance(Charge.objects.filter(student=student)).order_by("due_date"))
        self.assertEqual([b.outstanding for b in balances], [D("0"), D("1500"), D("3000"), D("3000")])

    def test_cannot_collect_more_than_due(self):
        student = self.enroll()
        with self.assertRaises(Conflict):
            services.collect(student=student, mode="cash", amount=D("12000.01"), received_by="acc")
        first = Charge.objects.filter(student=student).order_by("due_date").first()
        with self.assertRaises(Conflict):
            services.collect(student=student, mode="cash", lines=[services.LineIn(first, D("3000.01"))], received_by="acc")

    def test_cannot_pay_another_students_charge(self):
        a, b = self.enroll(), self.enroll()
        b_charge = Charge.objects.filter(student=b).first()
        with self.assertRaises(Conflict):
            services.collect(student=a, mode="cash", lines=[services.LineIn(b_charge, D("10"))], received_by="acc")

    def test_receipt_numbers_are_per_branch_and_financial_year(self):
        student = self.enroll()
        r1 = services.collect(student=student, mode="cash", amount=D("10"), received_by="x", on=date(2027, 3, 31))
        r2 = services.collect(student=student, mode="cash", amount=D("10"), received_by="x", on=date(2027, 4, 1))
        self.assertIn("/2026-27/00001", r1.number)
        self.assertIn("/2027-28/00001", r2.number)

    def test_post_charge_is_idempotent_per_source(self):
        student = self.make_student()
        a = services.post_charge(student=student, kind="hostel", amount=D("2500"), due_date=date(2026, 11, 1),
                                 description="Hostel Nov", source_type="hostel", source_id="alloc:1:2026-11")
        b = services.post_charge(student=student, kind="hostel", amount=D("2500"), due_date=date(2026, 11, 1),
                                 description="Hostel Nov", source_type="hostel", source_id="alloc:1:2026-11")
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Charge.objects.filter(student=student).count(), 1)

    def test_cancel_future_charges_keeps_paid_ones(self):
        student = self.make_student()
        for m in (11, 12):
            services.post_charge(student=student, kind="transport", amount=D("800"), due_date=date(2026, m, 5),
                                 description=f"Bus {m}", source_type="transport", source_id=f"asg:7:{m}")
        nov = Charge.objects.get(student=student, source_id="asg:7:11")
        services.collect(student=student, mode="cash", lines=[services.LineIn(nov, D("800"))], received_by="x")
        n = services.cancel_future_charges(student=student, source_type="transport", source_prefix="asg:7:",
                                           from_date=date(2026, 11, 1), reason="stopped")
        self.assertEqual(n, 1)
        self.assertIsNone(Charge.objects.get(source_id="asg:7:11").cancelled_at)
        self.assertIsNotNone(Charge.objects.get(source_id="asg:7:12").cancelled_at)

    def test_concession_never_exceeds_unpaid_amount(self):
        student = self.enroll()
        first = Charge.objects.filter(student=student).order_by("due_date").first()
        services.collect(student=student, mode="cash", lines=[services.LineIn(first, D("3000"))], received_by="x")
        c = Concession.objects.create(branch=self.branch, student=student, head=self.tuition, academic_year=self.year,
                                      kind="percent", value=D("50"), reason="merit")
        services.decide_concession(concession=c, approve=True, by="admin")
        first.refresh_from_db()
        self.assertEqual(first.discount, D("0"))  # already paid in full: no credit created
        self.assertEqual(self.dues(student), D("4500.00"))

    def test_refund_lowers_cash_paid_but_does_not_reopen_the_due(self):
        student = self.enroll()
        first = Charge.objects.filter(student=student).order_by("due_date").first()
        services.collect(student=student, mode="cash", lines=[services.LineIn(first, D("3000"))], received_by="x")
        with self.assertRaises(Conflict):
            services.refund(student=student, lines=[services.LineIn(first, D("3000.01"))], mode="cash", reason="r", by="x")
        services.refund(student=student, lines=[services.LineIn(first, D("1000"))], mode="cash", reason="r", by="x")
        bal = charges_with_balance(Charge.objects.filter(pk=first.pk)).get()
        self.assertEqual((bal.received, bal.paid, bal.outstanding), (D("3000.00"), D("2000.00"), D("0.00")))
        self.assertEqual(self.dues(student), D("9000.00"))  # the other three instalments only
        with self.assertRaises(Conflict):  # only the 2000 still kept can be refunded
            services.refund(student=student, lines=[services.LineIn(first, D("2000.01"))], mode="cash", reason="r", by="x")

    def test_cancelled_receipt_reopens_the_due(self):
        student = self.enroll()
        first = Charge.objects.filter(student=student).order_by("due_date").first()
        receipt = services.collect(student=student, mode="cheque", reference="CHQ-1", received_by="x",
                                   lines=[services.LineIn(first, D("3000"))])
        services.cancel_receipt(receipt=receipt, by="admin", reason="cheque bounced")
        self.assertEqual(self.dues(student), D("12000.00"))

    def test_student_totals(self):
        student = self.enroll()
        services.collect(student=student, mode="cash", amount=D("2000"), received_by="x")
        row = students_with_dues(Student.objects.filter(pk=student.pk), date(2026, 8, 1)).get()
        self.assertEqual((row.total_charged, row.total_paid, row.outstanding, row.overdue),
                         (D("12000.00"), D("2000.00"), D("10000.00"), D("4000.00")))

    def test_other_branch_cannot_see_or_collect(self):
        student = self.enroll()
        gaya = self.make_branch("gaya")
        gaya_acc = self.make_user(Role.ACCOUNTANT, branch=gaya)
        api = self.api(gaya_acc, branch=gaya)
        self.assertEqual(api.get("/api/fees/charges/").json()["count"], 0)
        r = api.post("/api/fees/receipts/", {"student": student.pk, "mode": "cash", "amount": "10"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)


class FeesReportTest(FeesBase):
    def test_outstanding_by_class_report(self):
        self.enroll()
        b = self.enroll()
        services.collect(student=b, mode="cash", amount=D("12000"), received_by="x")
        rows = self.api(self.accountant).get("/api/fees/reports/outstanding/").json()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["program"], rows[0]["section"]), ("Class 6", "A"))
        self.assertEqual(D(str(rows[0]["outstanding"])), D("12000.00"))
        self.assertEqual(rows[0]["students_with_dues"], 1)


class NumberWordsTest(EraTestCase):
    def test_indian_numbering(self):
        self.assertEqual(rupees_in_words(D("125050.50")), "One Lakh Twenty-Five Thousand Fifty Rupees and Fifty Paise Only")
        self.assertEqual(rupees_in_words(D("12000")), "Twelve Thousand Rupees Only")
        self.assertEqual(rupees_in_words(D("31415926")), "Three Crore Fourteen Lakh Fifteen Thousand Nine Hundred Twenty-Six Rupees Only")

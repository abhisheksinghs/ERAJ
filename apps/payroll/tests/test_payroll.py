"""Payroll acceptance scenarios (scope doc, Payroll 1–8) and guards. Real tenant schema.

    python manage.py test apps.payroll.tests.test_payroll

Expected figures are worked by hand in the comments (PAY-5: "the accountant
checks 3 sample staff against their own calculation").
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django_tenants.utils import schema_context
from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.models import AuditLog
from apps.core.testing import EraTestCase
from apps.hr import services as hr
from apps.hr.models import LeaveType, StaffProfile
from apps.payroll import calc, services
from apps.payroll.models import (
    ArrearPayment, DARate, Loan, PayCell, PayComponent, PayLevel, PayrollRun, PayRuleSet, Payslip, SalaryStructure,
    StatutorySettings,
)

D = Decimal
OCT, NOV, AUG, SEP = date(2026, 10, 1), date(2026, 11, 1), date(2026, 8, 1), date(2026, 9, 1)
PT_SLABS = [{"from": 0, "to": 25000, "amount": 0}, {"from": "25000.01", "to": 41666, "amount": 83},
            {"from": "41666.01", "to": 83333, "amount": 167}, {"from": "83333.01", "to": None, "amount": 208}]
TDS_SLABS = [{"from": 0, "to": 400000, "percent": 0}, {"from": 400000, "to": 800000, "percent": 5},
             {"from": 800000, "to": 1200000, "percent": 10}, {"from": 1200000, "to": 1600000, "percent": 15},
             {"from": 1600000, "to": 2000000, "percent": 20}, {"from": 2000000, "to": 2400000, "percent": 25},
             {"from": 2400000, "to": None, "percent": 30}]


def lines(slip) -> dict:
    out = {}
    for ln in slip.lines.all():
        out[ln.code] = out.get(ln.code, D(0)) + ln.amount
    return out


@freeze_time("2026-11-20 10:00:00+05:30")
class PayrollBase(EraTestCase):
    def setUp(self):
        super().setUp()
        b = self.branch
        StatutorySettings.objects.create(branch=b, pt_slabs=PT_SLABS, tds_slabs=TDS_SLABS)
        self.central = PayRuleSet.objects.create(branch=b, code="central-7cpc", name="Central 7th CPC", hra_x=30, hra_y=20, hra_z=10)
        self.bihar = PayRuleSet.objects.create(branch=b, code="bihar-7cpc", name="Bihar 7th CPC", hra_x=16, hra_y=8, hra_z=8)
        self.l6 = PayLevel.objects.create(branch=b, rule_set=self.central, code="6", sequence=6)
        for i, basic in enumerate([35400, 36500, 37600, 38700], start=1):
            PayCell.objects.create(branch=b, level=self.l6, index=i, basic=basic)
        self.l7 = PayLevel.objects.create(branch=b, rule_set=self.bihar, code="7", sequence=7)
        for i, basic in enumerate([44900, 46200, 47600], start=1):
            PayCell.objects.create(branch=b, level=self.l7, index=i, basic=basic)
        for rs in (self.central, self.bihar):
            DARate.objects.create(branch=b, rule_set=rs, effective_from=date(2026, 1, 1), percent=50)
        self.ta = PayComponent.objects.create(branch=b, rule_set=self.central, code="ta", name="Transport allowance",
                                              calc="fixed", value=1800, prorate=True)
        # A: central L6 cell 1, PF; B: Bihar L7 cell 1, NPS; C: contract, fixed basic, ESI
        self.a = self.make_staff(full_name="Anil Kumar", date_joined=date(2020, 4, 1))
        self.b = self.make_staff(full_name="Babita Devi", date_joined=date(2019, 4, 1))
        self.c = self.make_staff(full_name="Chhotu Ram", date_joined=date(2025, 4, 1), employment_type="contract")
        StaffProfile.objects.create(branch=b, staff=self.a, uan="100200300400", bank_account="1111222233", ifsc="SBIN0001234")
        StaffProfile.objects.create(branch=b, staff=self.b, pran="110011001100", bank_account="4444555566", ifsc="PUNB0123400")
        StaffProfile.objects.create(branch=b, staff=self.c, esic_ip="3100123456", bank_account="7777888899", ifsc="BKID0004321")
        self.sa = SalaryStructure.objects.create(branch=b, staff=self.a, rule_set=self.central, level=self.l6, cell_index=1,
                                                 city_class="Z", pf=True, pt=True, tds=False)
        self.sb = SalaryStructure.objects.create(branch=b, staff=self.b, rule_set=self.bihar, level=self.l7, cell_index=1,
                                                 city_class="Z", nps=True, pt=True, tds=False)
        self.sc = SalaryStructure.objects.create(branch=b, staff=self.c, rule_set=self.central, fixed_basic=12000,
                                                 da_applicable=False, hra_applicable=False, esi=True, pt=True, tds=False,
                                                 increment_month=0)
        self.acct = self.api(self.make_user("accountant"))
        self.admin = self.api(self.make_user("admin"))

    def run_locked(self, month):
        run = services.create_run(branch=self.branch, month=month, by="acct")
        services.submit(run=run, by="acct")
        return services.lock(run=run, by="acct")

    def slip(self, run, staff):
        return Payslip.objects.get(run=run, staff=staff)

    def post(self, client, url, body=None):
        return client.post(url, body or {}, content_type="application/json")


class Scenario1and5Test(PayrollBase):
    def test_scenario_payroll_1_three_structures_pf_nps_esi(self):
        run = services.create_run(branch=self.branch, month=OCT, by="acct")
        a, b, c = (lines(self.slip(run, s)) for s in (self.a, self.b, self.c))
        self.assertIn("pf", a)
        self.assertNotIn("nps", a)
        self.assertIn("nps", b)
        self.assertNotIn("pf", b)
        self.assertIn("esi", c)
        self.assertNotIn("pf", c)
        self.assertEqual(run.payslips.count(), 3)

    def test_scenario_payroll_5_figures_match_the_hand_calculation(self):
        r = self.post(self.acct, "/api/payroll/runs/", {"month": "2026-10-01"})
        self.assertEqual(r.status_code, 201, r.content)
        run = PayrollRun.objects.get(pk=r.json()["id"])
        # A — central L6 c1: basic 35,400; DA 50% 17,700; HRA Z 10% 3,540; TA 1,800 → gross 58,440.
        #     PF wages capped at 15,000 → PF 12% 1,800; PT slab 41,666–83,333 → 167; net 56,473.
        #     Employer: 12% of 15,000 = 1,800 = EPS 8.33% 1,250 + EPF 550.
        a = self.slip(run, self.a)
        self.assertEqual(lines(a), {"basic": 35400, "da": 17700, "hra": 3540, "ta": 1800, "pf": 1800, "pt": 167,
                                    "employer_epf": 550, "employer_eps": 1250})
        self.assertEqual((a.gross, a.total_deductions, a.net_pay), (58440, 1967, 56473))
        # B — Bihar L7 c1: basic 44,900; DA 50% 22,450; HRA Z 8% 3,592 → gross 70,942.
        #     NPS 10% of 67,350 = 6,735; employer 14% = 9,429; PT 167; net 64,040.
        b = self.slip(run, self.b)
        self.assertEqual(lines(b), {"basic": 44900, "da": 22450, "hra": 3592, "nps": 6735, "pt": 167, "employer_nps": 9429})
        self.assertEqual(b.net_pay, 64040)
        # C — contract: basic 12,000 + TA 1,800 = 13,800 (≤ 21,000 → ESI).
        #     ESI 0.75% = 103.50 → 104 (rounded up); employer 3.25% = 448.50 → 449; PT nil; net 13,696.
        c = self.slip(run, self.c)
        self.assertEqual(lines(c), {"basic": 12000, "ta": 1800, "esi": 104, "employer_esi": 449})
        self.assertEqual(c.net_pay, 13696)
        totals = self.acct.get(f"/api/payroll/runs/{run.pk}/").json()["totals"]
        self.assertEqual(totals["net"], "134209.00")


class Scenario2Test(PayrollBase):
    def test_scenario_payroll_2_two_unpaid_days_reduce_net_by_two_days_pay(self):
        d = self.make_staff(full_name="Dinesh Prasad", date_joined=date(2024, 4, 1))
        SalaryStructure.objects.create(branch=self.branch, staff=d, rule_set=self.bihar, fixed_basic=30000, da_applicable=False,
                                       hra_applicable=False, pt=True, tds=False, increment_month=0)
        run = services.create_run(branch=self.branch, month=NOV, by="acct")
        before = self.slip(run, d).net_pay  # 30,000 − PT 83 = 29,917
        self.assertEqual(before, 29917)
        lwp = LeaveType.objects.create(branch=self.branch, code="LWP", name="Leave without pay", paid=False)
        app = hr.apply_leave(staff=d, leave_type=lwp, start=date(2026, 11, 2), end=date(2026, 11, 3), by="hr")
        hr.approve_leave(application=app, by="hr")
        r = self.post(self.acct, f"/api/payroll/runs/{run.pk}/recompute/")
        self.assertEqual(r.status_code, 200, r.content)
        after = self.slip(run, d)
        self.assertEqual((after.lop_days, after.paid_days), (D("2"), D("28")))
        self.assertEqual(before - after.net_pay, 2000)  # 2 days of 30,000 ÷ 30
        # a PF member's earnings are prorated the same way (PF itself stays at the capped 1,800)
        hr.mark_day(branch=self.branch, on=date(2026, 11, 4), absent=[self.a.pk], by="hr", can_correct_past=True)
        services.recompute(run=run, by="acct")
        a = self.slip(run, self.a)
        self.assertEqual(a.lop_days, 1)
        self.assertEqual(lines(a)["basic"], 34220)  # 35,400 × 29/30


class Scenario3Test(PayrollBase):
    def test_scenario_payroll_3_advance_recovered_monthly(self):
        r = self.post(self.acct, "/api/payroll/loans/", {"staff": self.c.pk, "kind": "advance", "amount": "12000",
                                                          "monthly_recovery": "2000", "start_month": "2026-10-01"})
        self.assertEqual(r.status_code, 201, r.content)
        loan = Loan.objects.get(pk=r.json()["id"])
        oct_run = self.run_locked(OCT)
        oct_slip = self.slip(oct_run, self.c)
        rec = next(ln for ln in oct_slip.lines.all() if ln.code == f"loan-{loan.pk}")
        self.assertEqual(rec.amount, 2000)
        self.assertIn("balance ₹10,000", rec.name)
        self.assertEqual(oct_slip.net_pay, 13696 - 2000)
        loan.refresh_from_db()
        self.assertEqual(loan.balance, 10000)
        self.run_locked(NOV)
        loan.refresh_from_db()
        self.assertEqual(loan.balance, 8000)
        # a draft recompute does not touch the balance; only locking does
        self.assertEqual(Loan.objects.get(pk=loan.pk).status, "active")


class Scenario4Test(PayrollBase):
    def test_scenario_payroll_4_locked_month_refuses_edits_and_admin_reversal_is_recorded(self):
        run = services.create_run(branch=self.branch, month=OCT, by="acct")
        self.assertEqual(self.post(self.acct, f"/api/payroll/runs/{run.pk}/lock/").status_code, 409)  # review first
        self.assertEqual(self.post(self.acct, f"/api/payroll/runs/{run.pk}/submit/").status_code, 200)
        self.assertEqual(self.post(self.acct, f"/api/payroll/runs/{run.pk}/lock/").status_code, 200)
        # edits refused
        self.assertEqual(self.post(self.acct, f"/api/payroll/runs/{run.pk}/recompute/").status_code, 409)
        r = self.post(self.acct, "/api/payroll/one-time/", {"staff": self.a.pk, "month": "2026-10-01", "kind": "bonus", "amount": "500"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("locked", r.json()["detail"])
        with self.assertRaisesMessage(Conflict, "October 2026 is locked"):
            hr.mark_day(branch=self.branch, on=date(2026, 10, 15), absent=[self.a.pk], by="hr", can_correct_past=True)
        self.assertEqual(self.post(self.acct, "/api/payroll/runs/", {"month": "2026-10-01"}).status_code, 409)
        self.assertIn(self.acct.put(f"/api/payroll/payslips/{self.slip(run, self.a).pk}/", {}, content_type="application/json").status_code, (403, 405))
        # reversal: Admin only, with a reason
        self.assertEqual(self.post(self.acct, f"/api/payroll/runs/{run.pk}/reverse/", {"reason": "x"}).status_code, 403)
        self.assertEqual(self.post(self.admin, f"/api/payroll/runs/{run.pk}/reverse/", {}).status_code, 400)
        r = self.post(self.admin, f"/api/payroll/runs/{run.pk}/reverse/", {"reason": "DA keyed wrongly"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["status"], r.json()["reversal_reason"]), ("reversed", "DA keyed wrongly"))
        with schema_context("public"):
            log = AuditLog.objects.filter(action="payroll.run.reversed").first()
        self.assertEqual(log.detail["reason"], "DA keyed wrongly")
        # the month is open again and can be re-run
        self.assertEqual(self.post(self.acct, "/api/payroll/runs/", {"month": "2026-10-01"}).status_code, 201)

    def test_reversal_restores_loan_balance_and_only_latest_month(self):
        loan = services.create_loan(staff=self.c, kind="advance", amount=D(6000), monthly_recovery=D(2000),
                                    start_month=OCT, note="", by="acct")
        oct_run = self.run_locked(OCT)
        nov_run = self.run_locked(NOV)
        with self.assertRaisesMessage(Conflict, "reverse the latest month first"):
            services.reverse(run=oct_run, reason="x", by="admin")
        services.reverse(run=nov_run, reason="re-run", by="admin")
        loan.refresh_from_db()
        self.assertEqual(loan.balance, 4000)


class Scenario6Test(PayrollBase):
    def test_scenario_payroll_6_ecr_file(self):
        run = self.run_locked(OCT)
        r = self.acct.get(f"/api/payroll/runs/{run.pk}/ecr/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('filename="ECR-2026-10.txt"', r["Content-Disposition"])
        # UAN#~#NAME#~#GROSS#~#EPF#~#EPS#~#EDLI#~#EE#~#EPS contri#~#ER diff#~#NCP#~#refund
        self.assertEqual(r.content.decode(), "100200300400#~#ANIL KUMAR#~#58440#~#15000#~#15000#~#15000#~#1800#~#1250#~#550#~#0#~#0\n")
        StaffProfile.objects.filter(staff=self.a).update(uan="")
        r = self.acct.get(f"/api/payroll/runs/{run.pk}/ecr/")
        self.assertEqual(r.status_code, 409)
        self.assertIn("UAN missing for: Anil Kumar", r.json()["detail"])

    def test_esic_pt_bank_register_and_payslip_pdf(self):
        run = self.run_locked(OCT)
        esic = self.acct.get(f"/api/payroll/runs/{run.pk}/esic/").json()
        self.assertEqual(esic, [{"ip_number": "3100123456", "ip_name": "Chhotu Ram", "days_paid": 31,
                                 "total_monthly_wages": 13800, "reason_code": "", "last_working_day": ""}])
        pt = {r["name"]: r["professional_tax"] for r in self.acct.get(f"/api/payroll/runs/{run.pk}/pt-register/").json()}
        self.assertEqual(pt, {"Anil Kumar": 167.0, "Babita Devi": 167.0, "Chhotu Ram": 0})
        x = self.acct.get(f"/api/payroll/runs/{run.pk}/bank-sheet/?format=xlsx")
        from openpyxl import load_workbook

        ws = load_workbook(BytesIO(x.content)).active
        header = [c.value for c in ws[1]]
        self.assertEqual(header[:5], ["employee_code", "name", "bank_account", "ifsc", "net_pay"])
        self.assertIn("1111222233", [c.value for c in ws["C"]])  # kept as text, not a number
        reg = self.acct.get(f"/api/payroll/runs/{run.pk}/register/").json()
        self.assertEqual({r["name"]: r["net_pay"] for r in reg}["Anil Kumar"], 56473)
        pdf = self.acct.get(f"/api/payroll/runs/{run.pk}/payslips/")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))


class Scenario7and8Test(PayrollBase):
    def test_scenario_payroll_7_da_revised_three_months_back_pays_arrears_now(self):
        for m in (AUG, SEP, OCT):
            self.run_locked(m)
        r = self.post(self.acct, f"/api/payroll/rule-sets/{self.central.pk}/revise-da/",
                      {"percent": "53", "effective_from": "2026-08-01", "note": "DA order 2026-11"})
        self.assertEqual(r.status_code, 201, r.content)
        nov = services.create_run(branch=self.branch, month=NOV, by="acct")
        a = self.slip(nov, self.a)
        got = lines(a)
        # arrears: 3 months × 35,400 × 3% = 3 × 1,062 = 3,186; November DA at 53% = 18,762
        self.assertEqual(got["da_arrears"], 3186)
        self.assertEqual(got["da"], 18762)
        name = next(ln.name for ln in a.lines.all() if ln.code == "da_arrears")
        self.assertEqual(name, "DA arrears (Aug 2026–Oct 2026)")
        self.assertEqual(a.gross, 35400 + 18762 + 3540 + 1800 + 3186)
        self.assertEqual(a.net_pay, a.gross - 1800 - 167)  # PF wages still capped
        self.assertEqual(ArrearPayment.objects.filter(paid_in=a).count(), 3)
        self.assertNotIn("da_arrears", lines(self.slip(nov, self.c)))  # no DA on a fixed contract
        # recalculating the draft does not pay twice
        services.recompute(run=nov, by="acct")
        self.assertEqual(lines(self.slip(nov, self.a))["da_arrears"], 3186)
        services.submit(run=nov, by="acct")
        services.lock(run=nov, by="acct")
        self.assertEqual(services.due_arrears(staff=self.a, rule_set=self.central, before=date(2026, 12, 1)), [])
        # reversing November makes the arrears due again, exactly once
        services.reverse(run=nov, reason="re-run", by="admin")
        again = services.create_run(branch=self.branch, month=NOV, by="acct")
        self.assertEqual(lines(self.slip(again, self.a))["da_arrears"], 3186)

    def test_scenario_payroll_8_da_revision_touches_only_its_rule_set(self):
        for m in (SEP, OCT):
            self.run_locked(m)
        services.revise_da(rule_set=self.central, percent=D("53"), effective_from=SEP, by="acct")
        nov = services.create_run(branch=self.branch, month=NOV, by="acct")
        a, b = self.slip(nov, self.a), self.slip(nov, self.b)
        self.assertEqual(lines(a)["da_arrears"], 2124)  # 2 × 1,062
        self.assertEqual(a.da_percent, 53)
        self.assertNotIn("da_arrears", lines(b))
        self.assertEqual((b.da_percent, lines(b)["da"]), (50, 22450))
        self.assertEqual(b.net_pay, 64040)

    def test_nps_is_deducted_on_da_arrears(self):
        self.run_locked(OCT)
        services.revise_da(rule_set=self.bihar, percent=D("54"), effective_from=OCT, by="acct")
        nov = services.create_run(branch=self.branch, month=NOV, by="acct")
        b = lines(self.slip(nov, self.b))
        self.assertEqual(b["da_arrears"], 1796)  # 44,900 × 4%
        # NPS 10% × (basic 44,900 + DA 54% 24,246 + arrears 1,796) = 10% × 70,942 = 7,094.20 → 7,094
        self.assertEqual(b["nps"], 7094)


class LifecycleAndGuardsTest(PayrollBase):
    def test_annual_increment_moves_to_next_cell_once(self):
        run = services.create_run(branch=self.branch, month=date(2026, 7, 1), by="acct")
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.cell_index, 2)
        self.assertEqual(self.slip(run, self.a).basic_full, 36500)
        self.assertTrue(any("cell 1 → 2" in n for n in run.notes))
        services.recompute(run=run, by="acct")
        self.sa.refresh_from_db()
        self.assertEqual(self.sa.cell_index, 2)

    def test_new_joiner_is_not_incremented_and_is_paid_from_joining_date(self):
        e = self.make_staff(full_name="Esha", date_joined=date(2026, 11, 16))
        SalaryStructure.objects.create(branch=self.branch, staff=e, rule_set=self.central, level=self.l6, cell_index=1,
                                       da_applicable=False, hra_applicable=False, pt=False, tds=False, increment_month=11)
        run = services.create_run(branch=self.branch, month=NOV, by="acct")
        slip = self.slip(run, e)
        # 15 of 30 days: basic 35,400 → 17,700; TA 1,800 → 900
        self.assertEqual((slip.paid_days, slip.basic_full, slip.net_pay), (D("15"), 35400, 18600))
        self.assertTrue(any("Esha: increment not due" in n for n in run.notes))

    def test_staff_without_structure_is_listed_and_future_month_refused(self):
        self.make_staff(full_name="No Structure")
        run = services.create_run(branch=self.branch, month=OCT, by="acct")
        self.assertIn("No Structure: no salary structure", run.notes)
        with self.assertRaisesMessage(Conflict, "future month"):
            services.create_run(branch=self.branch, month=date(2026, 12, 1), by="acct")

    def test_permissions_teacher_hr_and_other_branch(self):
        teacher = self.api(self.make_user("teacher"))
        self.assertEqual(teacher.get("/api/payroll/structures/").status_code, 403)
        self.assertEqual(self.post(self.api(self.make_user("hr")), "/api/payroll/runs/", {"month": "2026-10-01"}).status_code, 403)
        other = self.make_branch("east")
        self.assertEqual(self.api(self.make_user("accountant", branch=other), branch=other).get("/api/payroll/structures/").json()["count"], 0)
        r = self.post(self.acct, "/api/payroll/structures/", {"staff": self.make_staff(branch=other).pk, "rule_set": self.central.pk,
                                                               "fixed_basic": "10000"})
        self.assertEqual(r.status_code, 400)

    def test_structure_validation(self):
        s = self.make_staff()
        body = {"staff": s.pk, "rule_set": self.central.pk, "level": self.l7.pk, "cell_index": 1}
        self.assertIn("another rule set", str(self.post(self.acct, "/api/payroll/structures/", body).json()))
        body.update(level=self.l6.pk, cell_index=9)
        self.assertIn("no cell 9", str(self.post(self.acct, "/api/payroll/structures/", body).json()))
        body.update(cell_index=1, pf=True, nps=True)
        self.assertIn("not both", str(self.post(self.acct, "/api/payroll/structures/", body).json()))
        body.update(nps=False)
        r = self.post(self.acct, "/api/payroll/structures/", body)
        self.assertEqual(r.status_code, 201, r.content)

    def test_settings_slabs_are_validated(self):
        sid = self.acct.get("/api/payroll/settings/current/").json()["id"]
        bad = [{"from": 0, "to": 1000, "amount": 0}, {"from": 500, "to": None, "amount": 10}]
        r = self.acct.patch(f"/api/payroll/settings/{sid}/", {"pt_slabs": bad}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("overlaps", str(r.json()))
        self.assertEqual(self.api(self.make_user("hr")).patch(f"/api/payroll/settings/{sid}/", {"pt_slabs": []},
                                                              content_type="application/json").status_code, 403)

    def test_staff_see_only_their_own_locked_payslips(self):
        user = self.make_user("teacher")
        self.a.user = user
        self.a.save()
        api = self.api(user)
        services.create_run(branch=self.branch, month=OCT, by="acct")
        self.assertEqual(api.get("/api/payroll/me/payslips/").json(), [])  # draft is not shown
        PayrollRun.objects.all().delete()
        self.run_locked(OCT)
        mine = api.get("/api/payroll/me/payslips/").json()
        self.assertEqual([p["staff"] for p in mine], [self.a.pk])
        self.assertTrue(api.get("/api/payroll/me/pdf/?month=2026-10").content.startswith(b"%PDF"))
        self.assertEqual(api.get("/api/payroll/payslips/").status_code, 403)

    def test_tds_24q_form16_statutory_and_ytd(self):
        self.sa.tds = True
        self.sa.fixed_monthly_tds = D(1500)
        self.sa.save()
        StaffProfile.objects.filter(staff=self.a).update(pan="ABCDE1234F")
        self.run_locked(SEP)
        self.run_locked(OCT)
        q2 = self.acct.get("/api/payroll/reports/tds-24q/?fy=2026&quarter=2").json()
        self.assertEqual([(r["pan"], r["month"], r["tds"]) for r in q2 if r["tds"]], [("ABCDE1234F", "2026-09", 1500.0)])
        f16 = {r["name"]: r for r in self.acct.get("/api/payroll/reports/form16/?fy=2026").json()}
        self.assertEqual((f16["Anil Kumar"]["tds_q2"], f16["Anil Kumar"]["tds_q3"], f16["Anil Kumar"]["tds_total"]), (1500, 1500, 3000))
        st = {r["month"]: r for r in self.acct.get("/api/payroll/reports/statutory/?fy=2026").json()}
        self.assertEqual((st["2026-10"]["pf_employee"], st["2026-10"]["esi_employer"], st["2026-10"]["tds"]), (1800, 449, 1500))
        ytd = {r["name"]: r for r in self.acct.get("/api/payroll/reports/ytd/?fy=2026").json()}
        self.assertEqual((ytd["Anil Kumar"]["months"], ytd["Anil Kumar"]["gross"]), (2, 116880))


class CalcTest(PayrollBase):
    def st(self, **kw):
        return calc.Statutory(pt_slabs=PT_SLABS, tds_slabs=TDS_SLABS, **kw)

    def test_tds_projection_new_regime_with_cess(self):
        # ₹1,50,000 a month → 18,00,000 a year; less 75,000 = 17,25,000 taxable.
        # 4–8L 20,000 + 8–12L 40,000 + 12–16L 60,000 + 1.25L × 20% 25,000 = 1,45,000; +4% cess = 1,50,800 → 12,567 a month.
        res = calc.compute(calc.Input(basic_full=D(150000), days_in_month=30, tds=True, months_left=12), self.st())
        self.assertEqual(res.tds, 12567)
        # ₹1,06,250 a month = 12,75,000 a year → 12,00,000 taxable → rebate → nil
        res = calc.compute(calc.Input(basic_full=D(106250), days_in_month=30, tds=True, months_left=12), self.st())
        self.assertEqual(res.tds, 0)
        # tax already deducted is spread over the remaining months
        res = calc.compute(calc.Input(basic_full=D(150000), days_in_month=30, tds=True, months_left=6,
                                      ytd_taxable=D(900000), ytd_tds=D(80000)), self.st())
        self.assertEqual(res.tds, calc.r((D(150800) - 80000) / 6))

    def test_esi_stops_above_ceiling_and_negative_net_is_refused(self):
        res = calc.compute(calc.Input(basic_full=D(21001), days_in_month=30, esi=True), self.st())
        self.assertEqual(res.amount("esi"), 0)
        with self.assertRaises(calc.NegativeNet):
            calc.compute(calc.Input(basic_full=D(1000), days_in_month=30,
                                    components=[calc.Component("gis", "GIS", "deduction", D(2000))]), self.st())

    def test_uncapped_pf_and_eps_split(self):
        res = calc.compute(calc.Input(basic_full=D(40000), days_in_month=30, pf=True), self.st(pf_cap_wages=False))
        self.assertEqual((res.amount("pf"), res.employer_eps, res.employer_epf), (4800, 1250, 3550))

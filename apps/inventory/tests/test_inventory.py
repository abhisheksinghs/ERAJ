"""Inventory acceptance scenarios (scope doc, Inventory 1–5), HR-1's inventory half,
mess cost per head and guards. Real tenant schema.

    python manage.py test apps.inventory.tests.test_inventory
"""
from datetime import date
from decimal import Decimal

from django_tenants.utils import schema_context
from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.models import AuditLog
from apps.core.testing import EraTestCase
from apps.inventory import services
from apps.inventory.models import IssueRecord, Item, PurchaseOrder, Requisition, StockMove, Store, Vendor
from apps.people.models import Department

D = Decimal


@freeze_time("2026-11-20 10:00:00+05:30")
class InventoryBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.store = Store.objects.create(branch=self.branch, name="Main store")
        self.office = Department.objects.create(branch=self.branch, name="Office")
        self.science = Department.objects.create(branch=self.branch, name="Science")
        self.vendor = Vendor.objects.create(branch=self.branch, name="Patna Stationers", gstin="10ABCDE1234F1Z5")
        self.paper = Item.objects.create(branch=self.branch, store=self.store, code="PAP-A4", name="A4 paper", unit="ream",
                                         reorder_level=D("5"))
        self.keeper_user = self.make_user("store")
        self.keeper = self.api(self.keeper_user)
        self.admin_user = self.make_user("admin")
        self.admin = self.api(self.admin_user)

    def post(self, client, url, body=None):
        return client.post(url, body or {}, content_type="application/json")


class Scenario1and2Test(InventoryBase):
    def test_scenario_inventory_1_purchase_fifty_reams_shows_stock_and_value(self):
        r = self.post(self.keeper, "/api/inventory/purchases/", {"vendor": self.vendor.pk, "bill_no": "INV-501", "bill_date": "2026-11-18",
                                                                  "lines": [{"item": self.paper.pk, "quantity": "50", "rate": "250"}]})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["total"], "12500.00")
        row = next(x for x in self.keeper.get("/api/inventory/reports/stock/").json() if x["code"] == "PAP-A4")
        self.assertEqual((row["quantity"], row["value"]), (50, 12500))
        self.assertEqual(self.post(self.keeper, "/api/inventory/purchases/", {"vendor": self.vendor.pk, "bill_no": "INV-501",
                         "bill_date": "2026-11-18", "lines": [{"item": self.paper.pk, "quantity": "1", "rate": "1"}]}).status_code, 400)

    def test_scenario_inventory_2_issue_48_puts_item_on_low_stock_list(self):
        services.direct_purchase(vendor=self.vendor, bill_no="B1", bill_date=date(2026, 11, 18),
                                 lines=[{"item": self.paper, "quantity": D(50), "rate": D(250)}], by="k")
        r = self.post(self.keeper, "/api/inventory/items/issue/", {"item": self.paper.pk, "quantity": "48", "department": self.office.pk})
        self.assertEqual(r.status_code, 201, r.content)
        low = self.keeper.get("/api/inventory/reports/stock/?low=1").json()
        self.assertEqual([(x["code"], x["quantity"]) for x in low], [("PAP-A4", 2)])
        with schema_context("public"):
            self.assertTrue(AuditLog.objects.filter(action="notify.staff", detail__event="inventory.low_stock").exists())
        r = self.post(self.keeper, "/api/inventory/items/issue/", {"item": self.paper.pk, "quantity": "3", "department": self.office.pk})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Only 2 ream of A4 paper", r.json()["detail"])
        cons = self.keeper.get("/api/inventory/reports/consumption/?from=2026-11-01&to=2026-11-30").json()
        self.assertEqual(cons, [{"department": "Office", "item": "A4 paper", "unit": "ream", "quantity": 48, "value": 12000}])

    def test_weighted_average_cost(self):
        services.direct_purchase(vendor=self.vendor, bill_no="B1", bill_date=date(2026, 11, 1),
                                 lines=[{"item": self.paper, "quantity": D(10), "rate": D(200)}], by="k")
        services.direct_purchase(vendor=self.vendor, bill_no="B2", bill_date=date(2026, 11, 2),
                                 lines=[{"item": self.paper, "quantity": D(30), "rate": D(240)}], by="k")
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.avg_cost, D("230"))  # (2,000 + 7,200) / 40
        move = services.issue(item=self.paper, quantity=D(4), department=self.office, by="k")
        self.assertEqual(move.value, D("-920.00"))


class Scenario3Test(InventoryBase):
    def test_scenario_inventory_3_projector_returned_damaged_shows_in_ledger(self):
        teacher = self.make_staff(full_name="Rekha Kumari", department=self.science)
        projector = Item.objects.create(branch=self.branch, store=self.store, code="PRJ-01", name="Projector", kind="returnable")
        services.opening_stock(item=projector, quantity=2, rate=45000, by="k")
        r = self.post(self.keeper, "/api/inventory/items/issue/", {"item": projector.pk, "quantity": "1", "staff": teacher.pk,
                                                                    "due_back": "2026-11-30"})
        self.assertEqual(r.status_code, 201, r.content)
        issue_id = r.json()["id"]
        held = self.keeper.get("/api/inventory/reports/with-staff/").json()
        self.assertEqual([(x["staff"], x["item"]) for x in held], [("Rekha Kumari", "Projector")])
        self.assertEqual(self.post(self.keeper, f"/api/inventory/issues/{issue_id}/close/", {"outcome": "damaged"}).status_code, 409)
        r = self.post(self.keeper, f"/api/inventory/issues/{issue_id}/close/", {"outcome": "damaged", "note": "Lamp cracked, fell from table"})
        self.assertEqual(r.status_code, 200, r.content)
        ledger = self.keeper.get(f"/api/inventory/items/{projector.pk}/ledger/").json()
        self.assertEqual([m["kind"] for m in ledger], ["opening", "issue", "damaged"])
        self.assertEqual(ledger[2]["note"], "Lamp cracked, fell from table")
        self.assertEqual(ledger[2]["staff"], "Rekha Kumari")
        projector.refresh_from_db()
        self.assertEqual(projector.quantity, 1)  # the damaged one is written off
        self.assertEqual(self.keeper.get("/api/inventory/reports/with-staff/").json(), [])
        with self.assertRaisesMessage(Conflict, "returnable: issue it to a staff member"):
            services.issue(item=projector, quantity=1, department=self.science, by="k")


class Scenario4Test(InventoryBase):
    def test_scenario_inventory_4_adjustment_refused_for_store_keeper_allowed_for_admin(self):
        services.direct_purchase(vendor=self.vendor, bill_no="B1", bill_date=date(2026, 11, 18),
                                 lines=[{"item": self.paper, "quantity": D(50), "rate": D(250)}], by="k")
        url = f"/api/inventory/items/{self.paper.pk}/adjust/"
        self.assertEqual(self.post(self.keeper, url, {"counted": "47", "reason": "Physical count"}).status_code, 403)
        self.assertEqual(self.post(self.admin, url, {"counted": "47"}).status_code, 400)
        r = self.post(self.admin, url, {"counted": "47", "reason": "Physical count 20 Nov: 3 reams damp"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["kind"], r.json()["quantity"]), ("adjust", "-3.000"))
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.quantity, 47)


class Scenario5Test(InventoryBase):
    def test_scenario_inventory_5_sixty_thousand_needs_two_approvals_then_partly_received(self):
        lab = Item.objects.create(branch=self.branch, store=self.store, code="MIC-01", name="Student microscope")
        r = self.post(self.keeper, "/api/inventory/requisitions/", {"department": self.science.pk, "purpose": "Biology lab",
                      "lines": [{"item": lab.pk, "quantity": "10", "estimated_rate": "6000"}]})
        self.assertEqual(r.status_code, 201, r.content)
        req_id = r.json()["id"]
        self.assertEqual((r.json()["total"], r.json()["approvals_needed"]), ("60000.00", 2))
        self.assertEqual(self.post(self.keeper, f"/api/inventory/requisitions/{req_id}/submit/").status_code, 200)
        self.assertEqual(self.post(self.keeper, f"/api/inventory/requisitions/{req_id}/approve/").status_code, 403)
        acct = self.api(self.make_user("accountant"))
        r = self.post(acct, f"/api/inventory/requisitions/{req_id}/approve/")
        self.assertEqual(r.json()["status"], "pending")
        self.assertEqual(self.post(acct, f"/api/inventory/requisitions/{req_id}/approve/").status_code, 409)
        po = self.post(self.keeper, "/api/inventory/orders/", {"vendor": self.vendor.pk, "requisition": req_id})
        self.assertEqual(po.status_code, 409)  # not fully approved yet
        r = self.post(self.admin, f"/api/inventory/requisitions/{req_id}/approve/")
        self.assertEqual((r.json()["status"], len(r.json()["approved_by"])), ("approved", 2))
        po = self.post(self.keeper, "/api/inventory/orders/", {"vendor": self.vendor.pk, "requisition": req_id})
        self.assertEqual(po.status_code, 201, po.content)
        po = po.json()
        self.assertRegex(po["number"], r"^PO/MAIN/2026-27/0001$")
        line = po["lines"][0]["id"]
        r = self.post(self.keeper, f"/api/inventory/orders/{po['id']}/receive/", {"lines": {str(line): "6"}, "challan_no": "CH-9"})
        self.assertEqual(r.status_code, 201, r.content)
        po = self.keeper.get(f"/api/inventory/orders/{po['id']}/").json()
        self.assertEqual((po["status"], po["received_percent"]), ("partly", 60))
        self.assertEqual(self.post(self.keeper, f"/api/inventory/orders/{po['id']}/receive/", {"lines": {str(line): "5"}}).status_code, 409)
        lab.refresh_from_db()
        self.assertEqual((lab.quantity, lab.avg_cost), (6, 6000))
        pdf = self.keeper.get(f"/api/inventory/orders/{po['id']}/pdf/")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(Requisition.objects.get(pk=req_id).status, "ordered")
        vend = self.keeper.get("/api/inventory/reports/vendors/?from=2026-11-01&to=2026-11-30").json()
        self.assertEqual((vend[0]["vendor"], vend[0]["value"]), ("Patna Stationers", 36000))

    def test_small_requisition_needs_one_approval_and_requester_cannot_approve(self):
        req = services.create_requisition(department=self.office, purpose="", by=self.admin_user.email,
                                          lines=[{"item": self.paper, "quantity": D(10), "estimated_rate": D(250)}])
        services.submit_requisition(requisition=req, by=self.admin_user.email)
        with self.assertRaisesMessage(Conflict, "someone else"):
            services.approve_requisition(requisition=req, user=self.admin_user)
        req = services.approve_requisition(requisition=req, user=self.make_user("accountant"))
        self.assertEqual((req.approvals_needed, req.status), (1, "approved"))


class IntegrationTest(InventoryBase):
    def test_hr_1_new_staff_member_is_an_eligible_recipient(self):
        hr = self.api(self.make_user("hr"))
        staff_id = self.post(hr, "/api/people/staff/", {"employee_code": "T-900", "full_name": "Nisha Raj",
                                                         "department": self.science.pk}).json()["id"]
        services.direct_purchase(vendor=self.vendor, bill_no="B1", bill_date=date(2026, 11, 18),
                                 lines=[{"item": self.paper, "quantity": D(10), "rate": D(250)}], by="k")
        r = self.post(self.keeper, "/api/inventory/items/issue/", {"item": self.paper.pk, "quantity": "2", "staff": staff_id})
        self.assertEqual(r.status_code, 201, r.content)
        move = StockMove.objects.get(pk=r.json()["id"])
        self.assertEqual((move.staff_id, move.department_id), (staff_id, self.science.pk))

    def test_mess_store_cost_per_head(self):
        from apps.hostel.models import Mess, MessMember

        mess = Mess.objects.create(branch=self.branch, name="Boys mess")
        ms = Store.objects.create(branch=self.branch, name="Mess store", kind="mess", mess=mess)
        rice = Item.objects.create(branch=self.branch, store=ms, code="RICE", name="Rice", unit="kg")
        services.direct_purchase(vendor=self.vendor, bill_no="R1", bill_date=date(2026, 11, 2),
                                 lines=[{"item": rice, "quantity": D(300), "rate": D(40)}], by="k")
        services.issue(item=rice, quantity=D("150"), department=self.office, by="k")  # ₹6,000 to the kitchen
        for _ in range(2):
            MessMember.objects.create(branch=self.branch, mess=mess, student=self.make_student(), start_date=date(2026, 11, 1))
        warden = self.api(self.make_user("warden"))
        r = warden.get(f"/api/hostel/messes/{mess.pk}/cost-per-head/?month=2026-11").json()
        # 2 members × 30 days = 60 member-days; ₹6,000 ÷ 60 = ₹100
        self.assertEqual((r["member_days"], r["provisions_value"], r["provisions_per_head_day"]), (60, 6000, 100))

    def test_guards(self):
        self.assertEqual(self.api(self.make_user("teacher")).get("/api/inventory/items/").status_code, 403)
        other = self.make_branch("east")
        s = self.make_staff(branch=other)
        r = self.post(self.keeper, "/api/inventory/items/issue/", {"item": self.paper.pk, "quantity": "1", "staff": s.pk})
        self.assertEqual(r.status_code, 400)
        r = self.post(self.keeper, "/api/inventory/vendors/", {"name": "X", "gstin": "bad"})
        self.assertEqual(r.status_code, 400)
        r = self.post(self.keeper, "/api/inventory/vendors/", {"name": "Y", "gstin": "10abcde1234f1z5"})
        self.assertEqual(r.json()["gstin"], "10ABCDE1234F1Z5")
        self.assertFalse(IssueRecord.objects.exists())
        self.assertFalse(PurchaseOrder.objects.exists())

"""Library fines on the student's fee account (scope: "Library fines posted
into Fees"). Real tenant schema.

    python manage.py test apps.library.tests.test_fines_to_fees
"""
from decimal import Decimal
from unittest import mock

from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.fees import services as fees
from apps.fees.models import Charge, FeeHead
from apps.fees.selectors import charges_with_balance
from apps.library import services
from apps.library.models import Book, Member


class FinesToFeesTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            branch=self.branch, title="Godan", author="Premchand", isbn="G-1", copies_total=2, copies_available=2
        )
        self.student = self.make_student()
        self.member = self.make_member(student=self.student)

    def _late_return(self, member=None):
        with freeze_time("2026-07-01"):
            issue = services.issue_book(book=self.book, member=member or self.member)
        with freeze_time("2026-07-31"):  # due after 14 days → 16 days late
            _, fine = services.return_book(issue=issue)
        return fine

    def test_student_fine_is_billed_to_fee_account(self):
        fine = self._late_return()
        self.assertIsNotNone(fine.charge)
        charge = fine.charge
        self.assertEqual(charge.student, self.student)
        self.assertEqual(charge.amount, fine.amount)
        self.assertEqual(charge.source_type, Charge.Source.LIBRARY)
        self.assertEqual(charge.head.kind, FeeHead.Kind.LIBRARY_FINE)
        self.assertIn("Godan", charge.description)

    def test_paying_at_fee_counter_settles_the_fine(self):
        fine = self._late_return()
        librarian = self.api(self.make_user("librarian"))
        row = librarian.get(f"/api/library/fines/{fine.pk}/").json()
        self.assertEqual((row["status"], row["in_fees"], row["can_mark_paid"]), ("open", True, False))

        fees.collect(student=self.student, mode="cash", received_by="counter", amount=fine.amount)
        row = librarian.get(f"/api/library/fines/{fine.pk}/").json()
        self.assertEqual(row["status"], "paid")
        self.assertEqual(Decimal(row["outstanding"]), Decimal("0"))
        paid = librarian.get("/api/library/fines/?status=paid").json()
        self.assertEqual([r["id"] for r in paid["results"]], [fine.pk])

    def test_billed_fine_cannot_be_marked_paid_at_library_desk(self):
        fine = self._late_return()
        r = self.api(self.make_user("librarian")).patch(
            f"/api/library/fines/{fine.pk}/", {"paid": True}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("fee counter", str(r.json()))

    def test_waiving_cancels_the_unpaid_charge(self):
        fine = self._late_return()
        r = self.api(self.make_user("admin")).post(f"/api/library/fines/{fine.pk}/waive/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "waived")
        self.assertFalse(charges_with_balance(Charge.objects.filter(pk=fine.charge_id)).exists())

    def test_waiving_after_payment_is_refused(self):
        fine = self._late_return()
        fees.collect(student=self.student, mode="cash", received_by="counter", amount=fine.amount)
        with self.assertRaises(Conflict):
            services.waive_fine(fine=fine, by="admin@x")
        fine.refresh_from_db()
        self.assertFalse(fine.waived)

    def test_staff_fine_stays_at_library_desk(self):
        staff_member = Member.objects.create(branch=self.branch, staff=self.make_staff())
        fine = self._late_return(member=staff_member)
        self.assertIsNone(fine.charge)
        row = self.api(self.make_user("librarian")).get(f"/api/library/fines/{fine.pk}/").json()
        self.assertTrue(row["can_mark_paid"])

    def test_not_billed_when_institution_has_no_fees_module(self):
        with mock.patch("apps.core.licensing.get_subscription_state", return_value={"status": "active", "modules": ["library"]}):
            fine = self._late_return()
        self.assertIsNone(fine.charge)
        self.assertFalse(Charge.objects.filter(student=self.student).exists())

"""Lending workflow — availability, fines, renewals, holds. Real tenant schema.

    python manage.py test apps.library.tests.test_lending
"""
from decimal import Decimal

from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.library import services
from apps.library.models import Book, Hold


class LendingTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            branch=self.branch, title="T", author="A", isbn="I-1", copies_total=1, copies_available=1
        )
        self.m1 = self.make_member()
        self.m2 = self.make_member()

    def test_issue_decrements_and_blocks_at_zero(self):
        services.issue_book(book=self.book, member=self.m1)
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 0)
        with self.assertRaises(Conflict):
            services.issue_book(book=self.book, member=self.m2)

    def test_return_increments_and_fines_when_overdue(self):
        with freeze_time("2026-01-01"):
            issue = services.issue_book(book=self.book, member=self.m1)
        with freeze_time("2026-03-01"):
            _, fine = services.return_book(issue=issue)
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 1)
        self.assertIsNotNone(fine)
        self.assertGreater(fine.amount, Decimal("0"))

    def test_renew_until_limit(self):
        issue = services.issue_book(book=self.book, member=self.m1)
        services.renew_issue(issue=issue)
        services.renew_issue(issue=issue)
        issue.refresh_from_db()
        self.assertEqual(issue.renewals, 2)
        with self.assertRaises(Conflict):
            services.renew_issue(issue=issue)

    def test_renew_blocked_by_waiting_hold(self):
        issue = services.issue_book(book=self.book, member=self.m1)
        Hold.objects.create(branch=self.branch, book=self.book, member=self.m2)
        with self.assertRaises(Conflict):
            services.renew_issue(issue=issue)

    def test_hold_promoted_on_return(self):
        issue = services.issue_book(book=self.book, member=self.m1)
        hold = Hold.objects.create(branch=self.branch, book=self.book, member=self.m2)
        services.return_book(issue=issue)
        hold.refresh_from_db()
        self.assertEqual(hold.status, Hold.Status.READY)

    def test_borrow_limit_enforced(self):
        self.m1.max_books = 1
        self.m1.save()
        book2 = Book.objects.create(
            branch=self.branch, title="T2", author="A", isbn="I-2", copies_total=1, copies_available=1
        )
        services.issue_book(book=self.book, member=self.m1)
        with self.assertRaises(Conflict):
            services.issue_book(book=book2, member=self.m1)

    def test_book_and_member_from_different_branches_conflict(self):
        other = self.make_branch("other")
        stranger = self.make_member(student=self.make_student(branch=other))
        with self.assertRaises(Conflict):
            services.issue_book(book=self.book, member=stranger)

"""Lending workflow. All the inventory-mutating paths take a row lock on the
Book so two concurrent issues can't drive `copies_available` negative."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.library.models import Book, Fine, Hold, Issue


@transaction.atomic
def issue_book(*, book: Book, member) -> Issue:
    book = Book.objects.select_for_update().get(pk=book.pk)
    if book.copies_available < 1:
        raise Conflict("No copies available.")
    if member.open_loan_count >= member.effective_borrow_limit:
        raise Conflict(f"Member is at their borrow limit ({member.effective_borrow_limit}).")
    if member.issues.filter(book=book, returned_at__isnull=True).exists():
        raise Conflict("Member already has this title on loan.")

    book.copies_available -= 1
    book.save(update_fields=["copies_available", "updated_at"])
    issue = Issue.objects.create(
        book=book,
        member=member,
        due_date=timezone.localdate() + timedelta(days=settings.LIBRARY_LOAN_DAYS),
    )
    record("library.issue", detail={"issue": issue.pk, "book": book.pk, "member": member.pk})
    return issue


@transaction.atomic
def return_book(*, issue: Issue):
    if issue.returned_at:
        raise Conflict("This loan is already closed.")
    book = Book.objects.select_for_update().get(pk=issue.book_id)

    issue.returned_at = timezone.now()
    issue.save(update_fields=["returned_at", "updated_at"])
    book.copies_available = min(book.copies_available + 1, book.copies_total)
    book.save(update_fields=["copies_available", "updated_at"])

    fine = None
    overdue_days = (timezone.localdate() - issue.due_date).days
    if overdue_days > 0:
        fine = Fine.objects.create(
            member=issue.member,
            issue=issue,
            amount=Decimal(overdue_days) * settings.LIBRARY_FINE_PER_DAY,
            reason=f"{overdue_days} day(s) overdue",
        )

    next_hold = book.holds.filter(status=Hold.Status.WAITING).order_by("created_at").first()
    if next_hold:
        next_hold.status = Hold.Status.READY
        next_hold.save(update_fields=["status", "updated_at"])

    record("library.return", detail={"issue": issue.pk, "fine": fine.pk if fine else None})
    return issue, fine


@transaction.atomic
def renew_issue(*, issue: Issue) -> Issue:
    if issue.returned_at:
        raise Conflict("This loan is closed.")
    if issue.renewals >= settings.LIBRARY_MAX_RENEWALS:
        raise Conflict(f"Renewal limit reached ({settings.LIBRARY_MAX_RENEWALS}).")
    if issue.book.holds.filter(status=Hold.Status.WAITING).exists():
        raise Conflict("Another member is waiting for this title.")

    issue.renewals += 1
    base = max(issue.due_date, timezone.localdate())
    issue.due_date = base + timedelta(days=settings.LIBRARY_LOAN_DAYS)
    issue.save(update_fields=["renewals", "due_date", "updated_at"])
    record("library.renew", detail={"issue": issue.pk, "due_date": str(issue.due_date)})
    return issue


@transaction.atomic
def waive_fine(*, fine: Fine, by: str) -> Fine:
    if fine.waived:
        raise Conflict("Already waived.")
    fine.waived = True
    fine.waived_by = by
    fine.save(update_fields=["waived", "waived_by", "updated_at"])
    record("library.fine_waived", actor=by, detail={"fine": fine.pk, "amount": str(fine.amount)})
    return fine

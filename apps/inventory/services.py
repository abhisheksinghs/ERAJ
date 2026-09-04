from django.db import transaction

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.inventory.models import Item, IssueRecord
from django.utils import timezone


@transaction.atomic
def issue_item(*, item: Item, issued_to: str) -> IssueRecord:
    item = Item.objects.select_for_update().get(pk=item.pk)
    if item.quantity_available < 1:
        raise Conflict("No units available.")
    item.quantity_available -= 1
    item.save(update_fields=["quantity_available", "updated_at"])
    issue = IssueRecord.objects.create(item=item, issued_to=issued_to)
    record("inventory.issue", detail={"issue": issue.pk, "item": item.pk, "issued_to": issued_to})
    return issue


@transaction.atomic
def return_item(*, issue: IssueRecord) -> IssueRecord:
    if issue.returned_at:
        raise Conflict("Already returned.")
    item = Item.objects.select_for_update().get(pk=issue.item_id)
    issue.returned_at = timezone.now()
    issue.save(update_fields=["returned_at", "updated_at"])
    item.quantity_available = min(item.quantity_available + 1, item.quantity_total)
    item.save(update_fields=["quantity_available", "updated_at"])
    record("inventory.return", detail={"issue": issue.pk})
    return issue

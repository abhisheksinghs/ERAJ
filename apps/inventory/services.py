"""Inventory rules (ADR-010): stock ledger with weighted-average cost, issue/return,
adjustment, requisition approvals by amount, purchase orders and goods receipts."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.inventory.models import (
    DirectPurchase, DirectPurchaseLine, GoodsReceipt, GoodsReceiptLine, InventorySettings, IssueRecord, Item, POCounter,
    POLine, PurchaseOrder, Requisition, RequisitionApproval, RequisitionLine, StockMove, Store,
)

ZERO = Decimal("0")
DEFAULT_LEVELS = [{"up_to": 50000, "approvals": 1}, {"up_to": None, "approvals": 2}]


def money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def settings_for(branch) -> InventorySettings:
    obj, _ = InventorySettings.objects.get_or_create(branch=branch, defaults={"approval_levels": DEFAULT_LEVELS})
    return obj


def default_store(branch) -> Store:
    store, _ = Store.objects.get_or_create(branch=branch, name="Main store", defaults={"kind": Store.Kind.GENERAL})
    return store


def _fmt(q: Decimal) -> str:
    q = Decimal(q).normalize()
    return f"{q:f}"


# ------------------------------------------------------------------ ledger core
def _move(*, item: Item, kind: str, qty: Decimal, rate: Decimal | None = None, by: str = "", at=None, **refs) -> StockMove:
    """Apply one move to a row-locked item. In-moves with a rate re-average the cost."""
    qty = Decimal(qty)
    new_qty = item.quantity + qty
    if new_qty < 0:
        raise Conflict(f"Only {_fmt(item.quantity)} {item.get_unit_display().lower()} of {item.name} in stock.")
    if qty > 0 and rate is not None and kind in (StockMove.Kind.RECEIPT, StockMove.Kind.PURCHASE, StockMove.Kind.OPENING):
        total_value = item.quantity * item.avg_cost + qty * Decimal(rate)
        item.avg_cost = (total_value / new_qty).quantize(Decimal("0.0001")) if new_qty else ZERO
        move_rate = Decimal(rate)
    else:
        move_rate = item.avg_cost
    item.quantity = new_qty
    item.save(update_fields=["quantity", "avg_cost", "updated_at"])
    return StockMove.objects.create(branch=item.branch, item=item, at=at or timezone.now(), kind=kind, quantity=qty,
                                    rate=move_rate, value=money(qty * move_rate), balance=new_qty, by=by, **refs)


def _locked(item: Item) -> Item:
    return Item.objects.select_for_update().get(pk=item.pk)


def _check_reorder(item: Item, before: Decimal) -> None:
    if item.reorder_level and before > item.reorder_level >= item.quantity:
        from apps.core import notify

        notify.staff_role(item.branch, "store", "inventory.low_stock",
                          f"{item.name} is down to {_fmt(item.quantity)} {item.get_unit_display().lower()} "
                          f"(reorder level {_fmt(item.reorder_level)}).")


@transaction.atomic
def opening_stock(*, item: Item, quantity, rate, by: str) -> StockMove:
    item = _locked(item)
    if item.moves.exists():
        raise Conflict("Opening stock is entered once, before any other movement.")
    return _move(item=item, kind=StockMove.Kind.OPENING, qty=Decimal(quantity), rate=Decimal(rate), by=by, note="Opening stock")


# ------------------------------------------------------------------ issue / return
@transaction.atomic
def issue(*, item: Item, quantity, by: str, staff=None, department=None, due_back: date | None = None, note: str = "",
          on: date | None = None):
    """Consumables to a department and/or staff member (gone for good); returnables to a staff member."""
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise Conflict("Quantity must be more than zero.")
    item = _locked(item)
    for other in (staff, department):
        if other is not None and other.branch_id != item.branch_id:
            raise Conflict("Item and recipient belong to different branches.")
    if staff is not None and staff.status != "active":
        raise Conflict(f"{staff.full_name} is not active staff.")
    if item.kind == Item.Kind.RETURNABLE and staff is None:
        raise Conflict(f"{item.name} is returnable: issue it to a staff member.")
    if item.kind == Item.Kind.CONSUMABLE and staff is None and department is None:
        raise Conflict("Choose a department or a staff member.")
    on = on or timezone.localdate()
    before = item.quantity
    move = _move(item=item, kind=StockMove.Kind.ISSUE, qty=-quantity, by=by, staff=staff,
                 department=department or (staff.department if staff else None), note=note)
    _check_reorder(item, before)
    rec = None
    if item.kind == Item.Kind.RETURNABLE:
        rec = IssueRecord.objects.create(branch=item.branch, item=item, staff=staff, department=move.department,
                                         quantity=quantity, issued_on=on, due_back=due_back, note=note)
        move.reference = f"ISSUE-{rec.pk}"
        move.save(update_fields=["reference"])
    record("inventory.issued", actor=by, item=item.pk, quantity=str(quantity), staff=getattr(staff, "pk", None),
           department=getattr(move.department, "pk", None))
    return rec or move


@transaction.atomic
def close_issue(*, issue: IssueRecord, outcome: str, by: str, note: str = "", on: date | None = None) -> IssueRecord:
    """Returnable comes back (returned) or is written off (damaged / lost)."""
    rec = IssueRecord.objects.select_for_update().get(pk=issue.pk)
    if rec.status != IssueRecord.Status.OUT:
        raise Conflict(f"Already closed ({rec.get_status_display().lower()}).")
    if outcome not in (IssueRecord.Status.RETURNED, IssueRecord.Status.DAMAGED, IssueRecord.Status.LOST):
        raise Conflict("Outcome is returned, damaged or lost.")
    if outcome != IssueRecord.Status.RETURNED and not note.strip():
        raise Conflict("Describe the damage or loss.")
    item = _locked(rec.item)
    ref = {"staff": rec.staff, "department": rec.department, "reference": f"ISSUE-{rec.pk}", "note": note}
    if outcome == IssueRecord.Status.RETURNED:
        _move(item=item, kind=StockMove.Kind.RETURN, qty=rec.quantity, by=by, **ref)
    else:
        # back from the staff member, then written off: the ledger shows both
        kind = StockMove.Kind.DAMAGED if outcome == IssueRecord.Status.DAMAGED else StockMove.Kind.LOST
        StockMove.objects.create(branch=item.branch, item=item, at=timezone.now(), kind=kind, quantity=ZERO,
                                 rate=item.avg_cost, value=money(-rec.quantity * item.avg_cost), balance=item.quantity,
                                 by=by, **ref)
    rec.status, rec.closed_on = outcome, on or timezone.localdate()
    rec.note = (rec.note + " | " if rec.note else "") + note if note else rec.note
    rec.save(update_fields=["status", "closed_on", "note", "updated_at"])
    record("inventory.issue_closed", actor=by, issue=rec.pk, outcome=outcome, note=note)
    return rec


@transaction.atomic
def adjust(*, item: Item, counted, reason: str, by: str) -> StockMove:
    """Set stock to a physical count (Admin only — enforced by the view's permission)."""
    if not reason.strip():
        raise Conflict("Give the reason for the adjustment.")
    counted = Decimal(counted)
    if counted < 0:
        raise Conflict("A count can't be negative.")
    item = _locked(item)
    diff = counted - item.quantity
    if diff == 0:
        raise Conflict("The count matches the stock; nothing to adjust.")
    move = _move(item=item, kind=StockMove.Kind.ADJUST, qty=diff, by=by, note=reason)
    record("inventory.adjusted", actor=by, item=item.pk, diff=str(diff), reason=reason)
    return move


# ------------------------------------------------------------------ requisitions
def approvals_needed(branch, total: Decimal) -> int:
    levels = settings_for(branch).approval_levels or DEFAULT_LEVELS
    for lvl in levels:
        top = lvl.get("up_to")
        if top in (None, "") or total <= Decimal(str(top)):
            return int(lvl.get("approvals", 1))
    return int(levels[-1].get("approvals", 1))


@transaction.atomic
def create_requisition(*, department, lines: list[dict], purpose: str, by: str) -> Requisition:
    if not lines:
        raise Conflict("Add at least one item.")
    req = Requisition.objects.create(branch=department.branch, department=department, purpose=purpose, requested_by=by)
    total = ZERO
    for ln in lines:
        if ln["item"].branch_id != department.branch_id:
            raise Conflict("Items must belong to the same branch.")
        RequisitionLine.objects.create(requisition=req, item=ln["item"], quantity=ln["quantity"], estimated_rate=ln["estimated_rate"])
        total += Decimal(ln["quantity"]) * Decimal(ln["estimated_rate"])
    req.total = money(total)
    req.approvals_needed = approvals_needed(department.branch, req.total)
    req.save(update_fields=["total", "approvals_needed", "updated_at"])
    record("inventory.requisition_created", actor=by, requisition=req.pk, total=str(req.total))
    return req


@transaction.atomic
def submit_requisition(*, requisition: Requisition, by: str) -> Requisition:
    req = Requisition.objects.select_for_update().get(pk=requisition.pk)
    if req.status != Requisition.Status.DRAFT:
        raise Conflict("Only a draft requisition can be sent for approval.")
    req.approvals_needed = approvals_needed(req.branch, req.total)
    req.status = Requisition.Status.PENDING
    req.save(update_fields=["status", "approvals_needed", "updated_at"])
    record("inventory.requisition_submitted", actor=by, requisition=req.pk, approvals_needed=req.approvals_needed)
    return req


@transaction.atomic
def approve_requisition(*, requisition: Requisition, user, note: str = "") -> Requisition:
    req = Requisition.objects.select_for_update().get(pk=requisition.pk)
    if req.status != Requisition.Status.PENDING:
        raise Conflict("This requisition is not awaiting approval.")
    if req.requested_by and req.requested_by == user.email:
        raise Conflict("You raised this requisition; someone else must approve it.")
    if req.approvals.filter(user=user).exists():
        raise Conflict("You have already approved this requisition; it needs another approver.")
    RequisitionApproval.objects.create(requisition=req, user=user, by=user.email, note=note)
    if req.approvals.count() >= req.approvals_needed:
        req.status = Requisition.Status.APPROVED
        req.save(update_fields=["status", "updated_at"])
    record("inventory.requisition_approved", actor=user.email, requisition=req.pk,
           approvals=req.approvals.count(), needed=req.approvals_needed)
    return req


@transaction.atomic
def reject_requisition(*, requisition: Requisition, by: str, note: str) -> Requisition:
    req = Requisition.objects.select_for_update().get(pk=requisition.pk)
    if req.status not in (Requisition.Status.PENDING, Requisition.Status.DRAFT):
        raise Conflict("Only a draft or pending requisition can be rejected.")
    if not note.strip():
        raise Conflict("Give a reason for rejecting.")
    req.status, req.decided_note = Requisition.Status.REJECTED, note
    req.save(update_fields=["status", "decided_note", "updated_at"])
    record("inventory.requisition_rejected", actor=by, requisition=req.pk, note=note)
    return req


# ------------------------------------------------------------------ purchase orders
def financial_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _next_po_number(branch, on: date) -> str:
    fy = financial_year(on)
    counter, _ = POCounter.objects.select_for_update().get_or_create(branch=branch, financial_year=fy)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"PO/{branch.code.upper()}/{fy}/{counter.last:04d}"


@transaction.atomic
def raise_order(*, vendor, lines: list[dict], by: str, requisition: Requisition | None = None, on: date | None = None,
                terms: str = "") -> PurchaseOrder:
    on = on or timezone.localdate()
    if requisition is not None:
        requisition = Requisition.objects.select_for_update().get(pk=requisition.pk)
        if requisition.status != Requisition.Status.APPROVED:
            raise Conflict("The requisition must be fully approved before ordering.")
        if not lines:
            lines = [{"item": ln.item, "quantity": ln.quantity, "rate": ln.estimated_rate} for ln in requisition.lines.all()]
    if not lines:
        raise Conflict("Add at least one item.")
    if vendor.branch_id != (requisition.branch_id if requisition else lines[0]["item"].branch_id):
        raise Conflict("Vendor belongs to another branch.")
    po = PurchaseOrder.objects.create(branch=vendor.branch, number=_next_po_number(vendor.branch, on), vendor=vendor,
                                      requisition=requisition, order_date=on, terms=terms, created_by=by)
    total = ZERO
    for ln in lines:
        if ln["item"].branch_id != po.branch_id:
            raise Conflict("Items must belong to the same branch.")
        POLine.objects.create(order=po, item=ln["item"], quantity=ln["quantity"], rate=ln["rate"])
        total += Decimal(ln["quantity"]) * Decimal(ln["rate"])
    po.total = money(total)
    po.save(update_fields=["total", "updated_at"])
    if requisition is not None:
        requisition.status = Requisition.Status.ORDERED
        requisition.save(update_fields=["status", "updated_at"])
    record("inventory.po_raised", actor=by, order=po.pk, number=po.number, total=str(po.total))
    return po


def _refresh_status(po: PurchaseOrder) -> None:
    lines = list(po.lines.all())
    if all(ln.received >= ln.quantity for ln in lines):
        po.status = PurchaseOrder.Status.RECEIVED
    elif any(ln.received > 0 for ln in lines):
        po.status = PurchaseOrder.Status.PARTLY
    else:
        po.status = PurchaseOrder.Status.OPEN
    po.save(update_fields=["status", "updated_at"])


@transaction.atomic
def receive(*, order: PurchaseOrder, quantities: dict[int, Decimal], by: str, challan_no: str = "",
            on: date | None = None) -> GoodsReceipt:
    """Goods received against an order, line by line ({po_line_id: qty}), up to what is outstanding."""
    po = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if po.status in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED):
        raise Conflict(f"Order {po.number} is {po.get_status_display().lower()}.")
    wanted = {int(k): Decimal(v) for k, v in quantities.items() if Decimal(v) != 0}
    if not wanted:
        raise Conflict("Enter the quantity received for at least one item.")
    lines = {ln.pk: ln for ln in POLine.objects.select_for_update().filter(order=po)}
    if set(wanted) - set(lines):
        raise Conflict("A line doesn't belong to this order.")
    grn = GoodsReceipt.objects.create(branch=po.branch, order=po, received_on=on or timezone.localdate(),
                                      challan_no=challan_no, received_by=by)
    for lid, qty in wanted.items():
        ln = lines[lid]
        if qty < 0 or qty > ln.outstanding:
            raise Conflict(f"{ln.item.name}: {_fmt(ln.outstanding)} still to come; {_fmt(qty)} entered.")
        GoodsReceiptLine.objects.create(receipt=grn, po_line=ln, quantity=qty)
        ln.received += qty
        ln.save(update_fields=["received"])
        _move(item=_locked(ln.item), kind=StockMove.Kind.RECEIPT, qty=qty, rate=ln.rate, by=by, vendor=po.vendor,
              reference=f"{po.number} / GRN-{grn.pk}", note=challan_no)
    _refresh_status(po)
    record("inventory.goods_received", actor=by, order=po.pk, grn=grn.pk, status=po.status)
    return grn


@transaction.atomic
def cancel_order(*, order: PurchaseOrder, by: str, reason: str) -> PurchaseOrder:
    po = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if po.status != PurchaseOrder.Status.OPEN:
        raise Conflict("Only an order with nothing received can be cancelled.")
    if not reason.strip():
        raise Conflict("Give the reason for cancelling.")
    po.status = PurchaseOrder.Status.CANCELLED
    po.save(update_fields=["status", "updated_at"])
    record("inventory.po_cancelled", actor=by, order=po.pk, reason=reason)
    return po


@transaction.atomic
def direct_purchase(*, vendor, bill_no: str, bill_date: date, lines: list[dict], by: str, note: str = "") -> DirectPurchase:
    if not lines:
        raise Conflict("Add at least one item.")
    if DirectPurchase.objects.filter(vendor=vendor, bill_no=bill_no).exists():
        raise Conflict(f"Bill {bill_no} from {vendor.name} is already recorded.")
    dp = DirectPurchase.objects.create(branch=vendor.branch, vendor=vendor, bill_no=bill_no, bill_date=bill_date, note=note,
                                       created_by=by)
    total = ZERO
    for ln in lines:
        if ln["item"].branch_id != vendor.branch_id:
            raise Conflict("Items must belong to the vendor's branch.")
        if Decimal(ln["quantity"]) <= 0:
            raise Conflict("Quantities must be more than zero.")
        DirectPurchaseLine.objects.create(purchase=dp, item=ln["item"], quantity=ln["quantity"], rate=ln["rate"])
        _move(item=_locked(ln["item"]), kind=StockMove.Kind.PURCHASE, qty=Decimal(ln["quantity"]), rate=Decimal(ln["rate"]),
              by=by, vendor=vendor, reference=f"Bill {bill_no}", note=note)
        total += Decimal(ln["quantity"]) * Decimal(ln["rate"])
    dp.total = money(total)
    dp.save(update_fields=["total", "updated_at"])
    record("inventory.direct_purchase", actor=by, purchase=dp.pk, total=str(dp.total))
    return dp


# ------------------------------------------------------------------ reports
def stock(*, branch, store=None, low_only: bool = False) -> list[dict]:
    qs = Item.objects.filter(branch=branch).select_related("store")
    if store is not None:
        qs = qs.filter(store=store)
    rows = []
    for it in qs:
        low = bool(it.reorder_level) and it.quantity <= it.reorder_level
        if low_only and not low:
            continue
        rows.append({"id": it.pk, "code": it.code, "name": it.name, "store": it.store.name, "category": it.category,
                     "unit": it.unit, "kind": it.kind, "quantity": it.quantity, "reorder_level": it.reorder_level,
                     "avg_cost": money(it.avg_cost), "value": money(it.quantity * it.avg_cost), "low": low})
    return rows


def ledger(item: Item, start: date | None = None, end: date | None = None) -> list[dict]:
    qs = item.moves.select_related("staff", "department", "vendor")
    if start:
        qs = qs.filter(at__date__gte=start)
    if end:
        qs = qs.filter(at__date__lte=end)
    return [{"at": m.at, "kind": m.kind, "kind_label": m.get_kind_display(), "quantity": m.quantity, "rate": money(m.rate),
             "value": m.value, "balance": m.balance, "staff": m.staff.full_name if m.staff else "",
             "department": m.department.name if m.department else "", "vendor": m.vendor.name if m.vendor else "",
             "reference": m.reference, "note": m.note, "by": m.by} for m in qs]


def consumption(*, branch, start: date, end: date, store=None) -> list[dict]:
    qs = StockMove.objects.filter(branch=branch, kind=StockMove.Kind.ISSUE, at__date__range=(start, end),
                                  item__kind="consumable")
    if store is not None:
        qs = qs.filter(item__store=store)
    out: dict[tuple, dict] = {}
    for dept, item, unit, q, v in qs.values_list("department__name", "item__name", "item__unit", "quantity", "value"):
        row = out.setdefault((dept or "—", item), {"department": dept or "—", "item": item, "unit": unit,
                                                   "quantity": ZERO, "value": ZERO})
        row["quantity"] -= q
        row["value"] -= v
    return sorted(out.values(), key=lambda r: (r["department"], r["item"]))


def with_staff(*, branch) -> list[dict]:
    return [{"id": r.pk, "staff": r.staff.full_name, "employee_code": r.staff.employee_code, "item": r.item.name,
             "code": r.item.code, "quantity": r.quantity, "issued_on": r.issued_on, "due_back": r.due_back,
             "overdue": bool(r.due_back and r.due_back < timezone.localdate())}
            for r in IssueRecord.objects.filter(branch=branch, status=IssueRecord.Status.OUT).select_related("staff", "item")
            .order_by("staff__full_name", "issued_on")]


def purchases_by_vendor(*, branch, start: date, end: date) -> list[dict]:
    qs = StockMove.objects.filter(branch=branch, kind__in=[StockMove.Kind.RECEIPT, StockMove.Kind.PURCHASE],
                                  at__date__range=(start, end), vendor__isnull=False)
    out: dict[str, dict] = defaultdict(lambda: {"value": ZERO, "lines": 0})
    for name, gstin, v in qs.values_list("vendor__name", "vendor__gstin", "value"):
        row = out[name]
        row.update(vendor=name, gstin=gstin)
        row["value"] += v
        row["lines"] += 1
    return sorted(out.values(), key=lambda r: -r["value"])


def mess_consumption_value(*, mess, start: date, end: date) -> Decimal:
    v = StockMove.objects.filter(item__store__mess=mess, kind=StockMove.Kind.ISSUE,
                                 at__date__range=(start, end)).aggregate(t=Sum("value"))["t"] or ZERO
    return -v


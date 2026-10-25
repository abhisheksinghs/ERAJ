"""
Tally export (scope: "receipts, refunds … as a file the accountant imports into
Tally"). Produces Tally's XML import envelope with one Receipt voucher per fee
receipt and one Payment voucher per refund.

Ledgers: debit the cash/bank ledger from FeeSettings, credit the fee head's
`tally_ledger` (or its name). Tally's XML convention: a debit is a negative
AMOUNT with ISDEEMEDPOSITIVE=Yes; a credit is positive with No.

Ledger names must already exist in the accountant's Tally company with these
exact names, or Tally rejects the voucher. To be confirmed against the client's
Tally version (open question in the scope document).
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from xml.sax.saxutils import escape

from apps.fees.models import Receipt, Refund
from apps.fees.services import settings_for


def _entry(ledger: str, amount: Decimal, debit: bool) -> str:
    signed = -amount if debit else amount
    return (
        "<ALLLEDGERENTRIES.LIST>"
        f"<LEDGERNAME>{escape(ledger)}</LEDGERNAME>"
        f"<ISDEEMEDPOSITIVE>{'Yes' if debit else 'No'}</ISDEEMEDPOSITIVE>"
        f"<AMOUNT>{signed:.2f}</AMOUNT>"
        "</ALLLEDGERENTRIES.LIST>"
    )


def _voucher(vtype: str, number: str, on: date, narration: str, entries: list[str]) -> str:
    return (
        '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
        f'<VOUCHER VCHTYPE="{vtype}" ACTION="Create">'
        f"<DATE>{on:%Y%m%d}</DATE>"
        f"<VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>"
        f"<VOUCHERNUMBER>{escape(number)}</VOUCHERNUMBER>"
        f"<NARRATION>{escape(narration)}</NARRATION>"
        + "".join(entries)
        + "</VOUCHER></TALLYMESSAGE>"
    )


def export_xml(*, branch, date_from: date, date_to: date) -> str:
    cfg = settings_for(branch)
    vouchers = []
    receipts = (
        Receipt.objects.filter(branch=branch, date__range=(date_from, date_to), cancelled_at__isnull=True)
        .select_related("student")
        .prefetch_related("lines__charge__head")
        .order_by("date", "sequence")
    )
    for r in receipts:
        money_ledger = cfg.cash_ledger if r.mode == Receipt.Mode.CASH else cfg.bank_ledger
        by_ledger: dict[str, Decimal] = defaultdict(Decimal)
        for line in r.lines.all():
            head = line.charge.head
            by_ledger[head.tally_ledger or head.name] += line.amount
        entries = [_entry(money_ledger, r.amount, debit=True)] + [
            _entry(ledger, amt, debit=False) for ledger, amt in sorted(by_ledger.items())
        ]
        narration = f"{r.student.full_name} ({r.student.admission_no}) {r.get_mode_display()} {r.reference}".strip()
        vouchers.append(_voucher("Receipt", r.number, r.date, narration, entries))

    refunds = Refund.objects.filter(branch=branch, date__range=(date_from, date_to)).select_related("student").prefetch_related("lines__charge__head")
    for f in refunds:
        money_ledger = cfg.cash_ledger if f.mode == Receipt.Mode.CASH else cfg.bank_ledger
        by_ledger: dict[str, Decimal] = defaultdict(Decimal)
        for line in f.lines.all():
            head = line.charge.head
            by_ledger[head.tally_ledger or head.name] += line.amount
        entries = [_entry(ledger, amt, debit=True) for ledger, amt in sorted(by_ledger.items())] + [
            _entry(money_ledger, f.amount, debit=False)
        ]
        vouchers.append(_voucher("Payment", f"RF-{f.pk}", f.date, f"Refund: {f.student.full_name} — {f.reason}", entries))

    company = f"<STATICVARIABLES><SVCURRENTCOMPANY>{escape(cfg.tally_company)}</SVCURRENTCOMPANY></STATICVARIABLES>" if cfg.tally_company else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>"
        "<BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME>"
        f"{company}</REQUESTDESC><REQUESTDATA>"
        + "".join(vouchers)
        + "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"
    )

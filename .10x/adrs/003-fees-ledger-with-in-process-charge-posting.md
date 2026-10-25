# ADR-003: Fees owns a per-student ledger; other modules post charges in-process

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1
**Author:** 10x-Team (Architect + Staff Engineer)

## Context
Hostel, Mess, Transport, Library fines and guest meals all create amounts a student owes.
The accountant must see one account per student with dues, receipts, concessions and late
fines, and receipts must be gap-free.

## Decision
- `apps.fees` models: `FeeHead`, `FeePlan` (program × year × head × instalments),
  `Charge` (student, head, period, due_date, amount, source_type/source_id), `Concession`
  (approved_by required to take effect), `Receipt` (gap-free number per branch per financial
  year via a locked counter row), `ReceiptLine` (allocates a receipt to charges), `Refund`.
- Other modules call `fees.services.post_charge(...)` / `cancel_future_charges(...)` inside
  their own `transaction.atomic` block. No signals, no Celery for money.
- Dues = sum(charges) − sum(concessions) − sum(allocated receipt lines), computed in SQL.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Django signals (`allocation_changed` exists today) | Loose coupling | Implicit; easy to lose a charge; harder to test | Money paths must be explicit |
| Celery event to post charges | Decoupled | Not in the same transaction; retries can double-post | Same |
| Each module keeps its own dues | Simple per module | No single student account; violates scope | Fails scope |

## Consequences
### Positive
- One transaction covers the business action and its charge; testable directly.
### Negative
- Hostel/Mess/Transport/Library import `apps.fees.services`.
### Risks
- Receipt-number contention under concurrency → one counter row per branch+FY with
  `select_for_update`; covered by a concurrency test.

## Dependencies
- ADR-001, ADR-002.

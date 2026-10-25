# ADR-007: Hostel blocks, contractor-run mess billing, visitors and outpasses

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1 (M2)
**Author:** 10x-Team (Architect + DBA + Senior Engineer)

## Context
Scope (Hostel and Mess; Visitors and outpass) needs blocks, room status, hostel fees on the
Fees account, a contractor-run mess charged either monthly or per day with a leave rebate,
guest meals, a daily headcount, a monthly contractor bill, complaints, an approved-visitor
list with a gate log, and outpasses that alert parents and count as mess leave.

## Decision
**Hostel**
- `Block` (code, name, gender) owns `Room`s; room numbers are unique per block. Room status:
  active / under repair / closed. An open repair ticket also blocks allocation.
- `HostelFeeRule` (block or all blocks, room type or any): a monthly amount. Allocating posts
  one Fees charge per month from the check-in month to the end of the academic year
  (`source_id = alloc:<id>:<YYYY-MM>`, due on the 10th). Vacating cancels the unpaid charges
  for months after the vacate month (`cancel_future_charges`); a month already paid stays.
- Vacate offers the bed to the first waiting student (unchanged).

**Mess** (all rows branch-owned, inside `apps.hostel`, served under `/api/hostel/mess-*`)
- `Mess`: contractor, the blocks it serves, monthly charge, per-day rate, rebate rule
  (minimum days + rebate per day), guest-meal rate. `MessMealRate`: the contractor's rate per
  plate per meal.
- `MessMember`: a student or staff member, plan = monthly | per_day, start/end dates.
  Residents are enrolled on allocation into their block's mess and ended on vacate.
- `MessLeave`: dates away. Approved outpasses create it automatically.
- Billing (`bill_mess_month`, idempotent per member-month, monthly Celery job + on enrolment):
  - monthly plan: billed in advance for month M = monthly charge (pro-rated by days enrolled
    in M) − rebate for qualifying leave taken in M−1 (each leave ≥ minimum days earns
    rebate/day × its days in M−1). Each rebate is kept in `MessRebate` (rebate register).
  - per-day plan: billed in arrears for month M−1 = per-day rate × (days enrolled − leave days).
  - Staff members are counted for headcount and the contractor bill but not billed through
    Fees (Fees is a student ledger); their mess recovery is a payroll deduction (M4).
- `GuestMeal` posts its charge immediately (count × guest-meal rate).
- Headcount for a date/meal = members enrolled that day − members on leave that day
  (+ guest meals). `MealCount` lets the warden record plates actually served.
- Contractor bill for a month = Σ over days and meals of plates × the meal's rate, where
  plates = the recorded `MealCount` or, if none, the expected headcount (flagged estimated).
- Provisions and cost per head use the Inventory "Mess store" and arrive with Inventory (M5).

**Gate**
- `ApprovedVisitor` per student (name, relation, phone, photo). `Visit` log: a visitor on the
  list goes in at once; anyone else waits as `held` until the warden approves.
- `Outpass`: requested → approved/rejected → out (gate check-out) → returned (check-in, late
  flagged against the expected return). Approval creates the matching `MessLeave`; an early
  return shortens it. Each step calls `apps.core.notify.guardian(...)`, which logs today and is
  replaced by the SMS/WhatsApp adapters in M7 (ADR-005).

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Separate `mess` Django app | Smaller apps | Module licensing and URLs are per app prefix; mess is sold with hostel | Keep one module |
| Bill mess monthly plan in arrears too | One rule for both plans | Scope: "the month's mess charge appears" on allocation | Advance for monthly |
| Post the rebate as a separate credit charge | Visible line | Credits are manual-only in the ledger (ADR-003) | Rebate inside the charge + register |
| Hostel fee via a FeePlan | Reuses plans | Plans are per class, hostel is per resident and stops on vacate | Rule + monthly charges |

## Consequences
### Positive
- Every hostel and mess amount lands on the one student account; vacate/leave rules are
  explicit and tested.
### Negative
- The vacate month's hostel and mess charges are not pro-rated back (stated to the client).
- Parent alerts are log-only until M7.

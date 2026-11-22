# ADR-010: Transport with stop fares and GPS; inventory with stock ledger and purchasing

**Status:** Accepted
**Date:** 2026-11-22
**Feature:** eraj-v1 (M5)
**Author:** 10x-Team (Architect + DBA + Security + Senior Engineer)

## Context
Scope doc, Transport: routes with ordered stops and times; fare per stop or distance slab added to
the student's Fees account; vehicles with capacity, driver/helper; vehicle documents with expiry
reminders; assignment refused when the vehicle is full; change/stop from a date with fees adjusting
from that month; staff riders; GPS live map, trip history, "bus near your stop" to parents and
over-speed to the in-charge; rider lists with guardian phones, occupancy, expiring documents.
Scenarios TR-1…6. The GPS provider is not yet named (open question).

Inventory: items (unit, location, consumable or returnable), vendors with GST, requisition →
approvals by amount → purchase order PDF → goods received in full or part; direct purchases;
issue consumables to a department or staff, returnables to staff and back (returned / damaged /
lost); reorder level alerts; Admin-only stock adjustment; stock value, low stock, item ledger,
department consumption, items with each staff member, purchases by vendor. Scenarios INV-1…5.
Hostel (M2) is waiting for a Mess store of provisions and a cost per head. HR-1 is waiting for
"issue to staff from the shared register".

The M0 stubs (free-text riders, one-unit issue records) are replaced; nothing is deployed, so
migrations are regenerated (as ADR-002 / ADR-009).

## Decision

### Transport (`apps.transport`)
- `Route` → `RouteStop` (sequence, name, pickup/drop time, lat/lng, distance km, optional monthly
  fare). `FareSlab` (from–to km → monthly fare) per branch. A stop's fare = its own fare, else the
  slab for its distance; no fare → assignment refused with a clear message.
- `Vehicle` (registration, type, capacity, route, driver/helper + phones, GPS device id, random
  push key, last position cache). `VehicleDocument` (insurance / fitness / permit / pollution /
  other, number, expiry, remind-days).
- `TransportAssignment`: exactly one of student or staff; route, stop, vehicle, start date, end
  date (null = riding), monthly fare snapshot. Capacity = riders whose period overlaps the new
  start, counted under `select_for_update` on the vehicle → the 41st on a 40-seat bus is refused.
- Fees (ADR-003, in the same transaction): a student's assignment posts one monthly charge per
  month from the start month to the end of the academic year (`transport` head, source id
  `assign:<id>:<YYYY-MM>`, due on the 10th, idempotent). Stopping from a date cancels unpaid
  charges from that month (from the next month if the date is mid-month); a change of stop or
  vehicle = stop + new assignment from the same date. Staff riders are not charged.
- GPS behind an adapter (ADR-005): `POST /api/transport/gps/push/` with `X-Device-Key` (any
  tracker or provider that can call a URL), plus a `Simulated` source that drives vehicles along
  their stops for staging (`simulate_gps` command). Each position → `VehiclePosition` history and
  the vehicle's last-position cache. `TransportSettings` per branch: speed limit (40 km/h),
  near-stop distance (500 m). Over the limit → `TransportAlert` (speed) to the in-charge, at most
  one per vehicle per 10 minutes. Within the distance of a stop on its route → one `TransportAlert`
  (near stop) per vehicle, stop, day and session (morning / afternoon) and a guardian alert to every
  student riding from that stop (via `apps.core.notify`, log-only until M6 channels).
- Live map page: Leaflet + OpenStreetMap tiles, polling every 15 s, position age shown; trip history
  as a line for a chosen date.
- Reports: rider list by route and stop with guardian phones (screen, Excel, PDF), occupancy,
  documents expiring within N days; daily reminder task logs expiring papers.

### Inventory (`apps.inventory`)
- `Store` (main / mess; the mess store links to a hostel `Mess`), `Item` (code, unit, category,
  consumable or returnable, location, reorder level, quantity, weighted-average cost), `Vendor`
  (GSTIN checked), `Department` from the people registry.
- `StockMove` is the ledger: every in and out (purchase receipt, direct purchase, issue, return,
  damaged, lost, adjustment) with quantity, rate, value, reference and note. Item quantity and
  average cost change only through `services`, under `select_for_update` on the item.
- Purchasing: `Requisition` (+ lines, estimated total) → approvals by amount from
  `InventorySettings.approval_levels` (sample: up to ₹50,000 one approval, above two); each approver
  is a distinct user holding `inventory.requisition.approve`, never the requester → `PurchaseOrder`
  (gap-free number per branch and financial year, PDF) → `GoodsReceipt` lines up to the outstanding
  quantity; order status open / partly received / received / cancelled. `DirectPurchase` (vendor,
  bill no., date, lines) for spot buys.
- Issue: consumables to a department and/or staff member (stock down for good); returnables only
  to a staff member, tracked on an `IssueRecord` until returned / damaged / lost (damaged and lost
  are written off). Falling to the reorder level alerts the store keeper (log until M6).
- Adjustment after a physical count: `inventory.stock.adjust` (Admin), reason required.
- Hostel: cost per head = value issued from the mess's store in the month ÷ member-days from the
  mess headcount.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Keep transport riders as free text | No registry link | No fees, no guardian alerts, scope needs register pick | Scope |
| Charge transport once per year | Simple | Scope: stop from a month must stop that month's fee | Monthly charges |
| Poll a GPS vendor API | Works when vendor can't push | Vendor unknown; needs credentials | Push + simulator now, poller adapter when named |
| Quantity field only (no ledger) | Simple | No item ledger, valuation, audit of who moved what | Ledger is the source of truth |
| FIFO valuation | Exact batch cost | Batches add complexity schools don't use | Weighted average |
| One approval regardless of amount | Simple | Scope sets levels by amount (INV-5) | Levels as data |

## Consequences
### Positive
- Transport fees, stops and alerts follow the student; inventory is auditable move by move.
- Mess provisions and HR-1 "issue to staff" are closed.
### Negative
- OpenStreetMap tiles load from the public tile servers (fine for an institution's volume; switch
  to a paid tile provider if usage grows).
- Near-stop alerts are only as fresh as the tracker's reporting interval.
### Risks
- GPS provider may only offer a pull API → add a poller adapter once named (open question).
- Push keys are bearer secrets → random 32-byte keys, rotatable, optional IP allow-list.

## Dependencies
- ADR-001, ADR-002, ADR-003 (charges), ADR-005 (adapters, log-only alerts), ADR-006 (RBAC),
  ADR-007 (mess headcount).

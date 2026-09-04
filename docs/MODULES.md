# Eraj — Library & Hostel modules

Both are `TENANT_APPS`: one copy of every table per tenant schema, no tenant FK.
Every endpoint is under the tenant subdomain, needs a tenant-bound JWT, and is
paginated (`?page=`, `PAGE_SIZE=25`), filterable (`django-filter`), searchable
(`?search=`) and orderable (`?ordering=`). Live schema at `/api/schema/`,
Swagger UI at `/api/docs/`.

Roles: `read_only` → GET only; `staff` → all methods; `owner` → also fine
waivers. Business-rule violations return **409** with `{"detail": "..."}`;
the inventory/capacity paths take a row lock so concurrent writes can't
oversell.

## Library  (`/api/library/`)

| Resource | Endpoint | Notes |
|---|---|---|
| Categories | `categories/` | CRUD |
| Books | `books/` | CRUD (soft-delete). `?search=`, `?available=true`, `?category=`, `?tag=`, `?published_year__gte=`. `copies_available` is derived — set `copies_total` only. |
| ISBN lookup | `GET books/lookup/?isbn=` | OpenLibrary metadata to prefill a Book form (502 on upstream failure) |
| Members | `members/` | CRUD (soft-delete). `max_books` overrides `LIBRARY_DEFAULT_BORROW_LIMIT` |
| Issues (loans) | `issues/` | `POST {book, member}` → issues if a copy is free, member under limit, no dup open loan. `?open=true`, `?overdue=true` |
| | `POST issues/{id}/return/` | frees the copy; accrues a `Fine` if overdue; promotes the oldest waiting hold |
| | `POST issues/{id}/renew/` | extends the due date; blocked at `LIBRARY_MAX_RENEWALS` or if a hold is waiting |
| Fines | `fines/` | list/retrieve; `PATCH {paid}` to settle |
| | `POST fines/{id}/waive/` | **owner only** |
| Holds | `holds/` | `POST {book, member}` only when no copies are free; `DELETE` cancels; oldest waiting hold goes `ready` on return |

Tunables (env): `LIBRARY_LOAN_DAYS` (14), `LIBRARY_MAX_RENEWALS` (2),
`LIBRARY_FINE_PER_DAY` (2.00), `LIBRARY_DEFAULT_BORROW_LIMIT` (5).

## Hostel  (`/api/hostel/`)

| Resource | Endpoint | Notes |
|---|---|---|
| Rooms | `rooms/` | CRUD (soft-delete). `number` unique; `room_type`, `gender`, `floor`, `status`. `?has_space=true`, `?status=`, `?gender=`, `?floor=` |
| Occupancy | `GET rooms/occupancy/` | per-room capacity / occupied / free (respects filters) |
| Residents | `residents/` | CRUD (soft-delete); `current_room` is derived from the active allocation |
| Allocations | `allocations/` | `POST {resident, room}` → allocates if the room is `active`, has a free bed, no open maintenance ticket, and the resident has no active allocation. `?active=true` |
| | `POST allocations/{id}/vacate/` | frees the bed, keeps the row as history, offers the room to the oldest waitlisted resident |
| Waitlist | `waitlist/` | `POST {resident, room}` only when the room is full; `DELETE` cancels; oldest entry goes `offered` on vacate |
| Maintenance | `maintenance/` | `POST {room, summary, details}`; `POST maintenance/{id}/close/`. An open ticket blocks allocation |

`hostel.services.allocation_changed` signal fires on allocate/vacate — no
receiver yet; the future Fees module hooks it.

## Tests

`apps/library/tests/test_lending.py`, `apps/hostel/tests/test_allocation.py`
(TenantTestCase) cover the workflow branches: availability/capacity limits,
fines, renewals, hold/waitlist promotion, maintenance blocking.

---

## The rest of the product line

Library and Hostel got the full workflow treatment (row-locked services,
fines/holds, waitlists). The remaining products from the spec are built
**lean** — CRUD plus the one core action each obviously needs, no invented
business rules (tax slabs, grading curves, routing algorithms) with no real
requirement behind them. Each still follows the same shape: models → (a
`services.py` only where there's an actual rule to enforce) → serializers →
ViewSet + router → migration → tests where there's branching logic to break.

Every module below returns 409 (not 500) on a business-rule conflict, is
paginated/filterable/searchable like Library/Hostel, and needs the same
tenant-bound JWT. No frontend pages yet — same `app/library/page.tsx`
pattern applies when they're wanted.

### Attendance (`/api/attendance/`)
`students/` (CRUD, own `Student` — module-local, see note below) ·
`GET students/{id}/summary/` (present/absent/leave counts + %) ·
`records/` (list/retrieve, filter by student/date/status) ·
`POST records/mark/` `{student, date, status}` — idempotent, re-marking a
day updates it instead of erroring.

### HR (`/api/hr/`)
`departments/`, `employees/` — plain CRUD, no workflow. `employees/` filters
by `department`/`is_active`.

### Payroll (`/api/payroll/`) — depends on HR's `Employee`
`payslips/`: `POST {employee, period, basic_salary, allowances, deductions}`
→ `net_pay` computed and stored; one payslip per employee per period
(409 on a duplicate). **Not statutory-compliant** — flat arithmetic, no
PF/ESI/TDS/tax-slab logic. Needs a compliance review before it touches a
real salary.

### Fees (`/api/fees/`)
`structures/` (CRUD: name, term, amount, due date) ·
`GET structures/{id}/collections/` (total collected + payment count) ·
`payments/`: `POST {fee_structure, payer_name, payer_reference, amount}` →
auto-generated `receipt_no`. No per-student invoice/ledger — "dues" (who
still owes what) needs an enrollment model this build doesn't have; only
collection totals are tracked, not outstanding balances.

### Exam (`/api/exam/`)
`students/` (CRUD, own `Student` model) · `subjects/` (CRUD) ·
`GET students/{id}/report/` (all results + overall %) · `results/`:
`POST results/record/` `{student, subject, exam_name, marks_obtained,
max_marks}` — idempotent per (student, subject, exam_name).

### Transport (`/api/transport/`)
`routes/`, `vehicles/` (CRUD; vehicle exposes `active_riders`/
`available_seats`) · `assignments/`: `POST {vehicle, rider_name,
rider_contact, pickup_point}` — row-locked capacity check against the
vehicle, 409 when full · `POST assignments/{id}/unassign/`. Riders are
freetext fields on the assignment, not a person registry — nothing else
needs to reference "who rides the bus".

### Inventory (`/api/inventory/`)
Structurally Library's `Book`/`Issue` renamed — `items/` (CRUD; `sku`
unique, `quantity_available` DB-constrained `0 <= available <= total`) ·
`issues/`: `POST {item, issued_to}` (row-locked, 409 at zero) ·
`POST issues/{id}/return/`. No due dates/fines — stock issue/return has no
lending-period concept.

### A note on "Student" appearing three times
Attendance and Exam each keep their own minimal `Student` model; Transport
doesn't have one at all. This is deliberate — see
`docs/REQUIREMENTS_GAP_ANALYSIS.md`'s modeling note: independent per-module
records over one shared cross-module registry, matching the Library
`Member` / Hostel `Resident` precedent. Real cost: enrolling a student
means separate data entry in Attendance and Exam today. Revisit with a
shared `apps.people` app if that duplication becomes a real complaint —
don't build it speculatively before it is one.

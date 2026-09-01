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

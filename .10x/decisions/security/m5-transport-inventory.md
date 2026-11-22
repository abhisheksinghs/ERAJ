# Security — M5 Transport + Inventory (2026-11-22)

| Threat | Control | Evidence |
|---|---|---|
| Forged GPS positions (fake "bus near stop" alerts) | per-vehicle random 32-byte push key, rotatable; optional IP allow-list; inactive vehicles refused | tests (403 bad key, 403 after rotation) |
| GPS key leakage via lists/exports | key shown only on the vehicle's own detail screen | test |
| Position flooding / nonsense | ≤1000 positions per call; lat/lng/speed range checks; duplicates ignored (unique vehicle+time) | tests (400) |
| Alert spam to parents | one near-stop alert per vehicle, stop, day and session; one over-speed alert per vehicle per 10 min | tests |
| Guardian phone numbers in rider lists | `transport.report.view` only (transport in-charge, Admin; accountant read) | RBAC |
| Over-capacity race | vehicle row lock during assignment | design + test |
| Store keeper writing stock off silently | adjustment is Admin-only with a reason; damaged/lost need a note; every move in the ledger with actor | INV-3/INV-4 tests |
| Requisition self-approval / double approval | requester can't approve; one approval per user; distinct approvers counted | tests |
| Over-receipt to inflate stock | receipt ≤ outstanding per line under order lock; DB check `received ≤ quantity` | test (409) |
| Cross-branch ids (stops, vehicles, items, staff, vendors) | Scoped FK fields, service-level branch checks | tests (400) |
| Duplicate bills | unique (vendor, bill no.) | test |

Open: `X-Forwarded-For` is trusted for the GPS/attendance IP allow-list — the reverse proxy must
overwrite (not append) it in production (M7 deploy config).

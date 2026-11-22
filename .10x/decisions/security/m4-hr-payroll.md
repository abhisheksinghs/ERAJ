# Security — M4 HR + Payroll (2026-11-22)

| Threat | Control | Evidence |
|---|---|---|
| Teacher/librarian reads colleagues' PAN, UAN, bank account | `hr.profile.view` only for HR, Admin, Accountant | test (403) |
| Bank account exposure in exports/lists | masked in list responses; full number only on the detail screen and the bank sheet (accountant) | test |
| Aadhaar over-collection | not stored (payroll doesn't need it) | ADR-009 |
| Malicious upload (exe renamed .pdf, HTML as PDF) | extension allow-list + magic-byte check + 5 MB cap; random stored name; `nosniff`; attachment disposition | tests |
| Document URL guessing | files served only by an authenticated, branch-scoped endpoint | design + test |
| Staff edits another person's leave/payslips | self endpoints resolve the login's own staff row; other ids → 404 | tests |
| Accountant rewrites a closed month | locked runs: no recompute/one-time/attendance/leave changes (409); reversal Admin-only with reason, audited | PAY-4 test |
| Cross-branch ids in payroll writes | BranchScopedSerializer + scoped nested component FK | test (400) |
| Slab JSON injection / nonsense | slabs validated (numbers, order, no overlap) | test |
| Spreadsheet formula injection in exports | existing `safe_cell` renderer | M1 tests |
| Vulnerable framework | Next.js 16.4.3 advisories (incl. response injection for self-hosted proxies) → 16.4.6 | `npm audit` 0 |

Open: per-field encryption of PAN/bank at rest (DB-level encryption + backups encrypted today);
decide with the client under DPDP; add HR/payroll data to docs/DPDP.md data map (done below).

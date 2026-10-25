# DBA — eraj-v1

**Date:** 2026-10-25 · **ADRs:** 001, 002

## Migrations
- All tenant-module migrations regenerated as clean `0001_initial` (M1). Hand-written migrations
  are not allowed; `makemigrations --check` passes ("No changes detected").
- `core` keeps 0001/0002 (unchanged, shared schema).
- Local/dev DBs from before M1 must be dropped and recreated (no client data existed).

## Branch ownership
| Model | Branch-owned | Uniqueness |
|---|---|---|
| org.Branch | — (is the branch) | `code` |
| org.RoleAssignment | branch nullable (group admin only) | (user, role, branch) NULLS NOT DISTINCT; check: NULL only for group_admin |
| people.AcademicYear | No — client-wide session | `name`; one `is_current` (partial unique) |
| people.Department / Program / Term / Subject / Section / Staff / Student / Guardian / StudentGuardian / Enrollment | Yes | per branch: department name, program code, subject code, employee_code, admission_no; Term (program, sequence); Section (year, program, term, name) NULLS NOT DISTINCT; Enrollment (student, year, term) NULLS NOT DISTINCT; one primary guardian per student |
| library.* | Yes | Book (branch, isbn); Category (branch, name); Member student XOR staff |
| hostel.* | Yes | Room (branch, number); one active allocation per student |
| attendance.AttendanceRecord | Yes | (student, date, period) NULLS NOT DISTINCT |
| exam.ExamResult | Yes | (student, subject, exam_name) |
| fees.* | Yes | Payment (branch, receipt_no) — replaced by gap-free ledger in M2 |
| payroll.Payslip | Yes | (staff, period) |
| transport.* | Yes | Route (branch, name); Vehicle (branch, number) |
| inventory.* | Yes | Item (branch, sku) |

`branch` FK is `PROTECT` + indexed on every branch-owned table; child rows carry their own
`branch` (denormalised) so every list filters on one indexed column.

## Indexing notes
- Every `branch_id` indexed (FK). Lists filter `branch_id IN (...)` first.
- `Guardian.phone`, `User.phone` indexed (portal OTP lookup, search).
- `AttendanceRecord.date` indexed (daily registers).
- Revisit with real data volumes (proposed target: 10,000 students / 500 staff per branch).

## Media
Uploads use `django_tenants.files.storage.TenantFileSystemStorage` → `MEDIA_ROOT/<schema>/…`.
Not served directly; authenticated download views to be added where files are shown.

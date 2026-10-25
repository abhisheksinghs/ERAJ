# ADR-002: Shared people registry, configurable academic structure, fresh migrations

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1
**Author:** 10x-Team (Architect + DBA)

## Context
Today each module keeps its own person record (Library `Member`, Hostel `Resident`,
Attendance/Exam `Student`, Transport freetext riders, HR `Employee`). The v1 scope requires a
student to be entered once and appear everywhere, per-student fee dues, and institutions of
different types (school classes/sections; college courses/semesters; coaching batches).
No client data exists in any deployed environment.

## Decision
- New tenant app `apps.people`: `AcademicYear`, `Program` (kind = school_class | course |
  batch), `Term` (semester/term; schools may use one), `Section`, `Subject` (credits optional),
  `Student`, `Guardian` (+ `StudentGuardian`), `Staff`, `Enrollment` (student × year × program
  × term × section — the single source of "which class is this student in").
- Modules FK into `people.Student` / `people.Staff`; module-local person models are removed
  (Library `Member` becomes a borrowing profile keyed to Student or Staff).
- HR's `Employee` becomes `people.Staff` (HR owns the screens and HR-only fields).
- All module migrations are regenerated with `makemigrations` into clean `0001_initial`
  files; hand-written migrations are not allowed (CI `makemigrations --check` is blocking).

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Keep per-module person models (status quo) | Zero coupling | Duplicate entry, no per-student fee ledger, scope requires single entry | Fails scope |
| Registry in `public` schema | One table | Cross-schema FKs are not possible under django-tenants; leaks PII scope | Not viable |
| Data-migrate existing migrations | Preserves history | No data exists to preserve; extra work and risk | YAGNI |

## Consequences
### Positive
- Single entry; Fees can compute dues per student; enrollment drives Attendance/Exam/Timetable.
- Fixes the `fees` migration drift by construction.
### Negative
- Modules now depend on `apps.people`; a people schema change ripples.
### Risks
- Rewritten migrations break any environment that already ran old ones → only local/dev DBs
  exist; they are dropped and recreated.

## Dependencies
- ADR-001 (Student/Staff/Enrollment are branch-owned). Constrains every module.

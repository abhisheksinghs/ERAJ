# ADR-006: Roles assigned per branch; a code-defined permission map

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1
**Author:** 10x-Team (Architect + Security)

## Context
Today `User.role` is owner | staff | read_only. v1 needs Admin, Group Admin, Accountant,
Teacher, Librarian, Warden, Transport, HR, Store, Parent and Student, scoped per branch, with
rules like "Accountant cannot cancel receipts", "teacher edits only own subject marks".

## Decision
- `accounts.RoleAssignment(user, role, branch nullable)`; `branch=NULL` only for Group Admin.
- `apps/accounts/rbac.py`: a dict `PERMISSIONS[role] -> set("module.action")`, e.g.
  `fees.receipt.cancel` only for Admin. One DRF permission class `HasPerm` reads
  `view.required_perms[action]`; a router-walking test fails for any ViewSet action without a
  declared permission. Object-level rules (own subject, own child) live in the ViewSet queryset.
- `/api/auth/me` returns branches, roles and the flattened permission set for the UI.
- Parents and students are `User`s linked to `Guardian`/`Student`; their querysets are
  restricted to their own children / themselves.
- `User.role` is removed (fresh migrations, ADR-002).

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Django Groups + model permissions | Built in | CRUD-only perms, no per-branch scope, no action perms | Doesn't express rules |
| django-guardian object perms | Object-level | Row explosion; slow lists | Overkill |

## Consequences
### Positive
- One place to read who can do what; UI menus come from the same map.
### Negative
- Permission changes need a deploy (acceptable for v1).
### Risks
- Missing declaration → default deny + router-walking test.

## Dependencies
- ADR-001.

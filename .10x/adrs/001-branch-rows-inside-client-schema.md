# ADR-001: Branches are rows inside the client's schema

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1
**Author:** 10x-Team (Architect + Staff Engineer); approved by Abhishek 2026-10-25

## Context
The client may run several branches under one trust/society and needs a group login, combined
reports and staff transfers between branches. Eraj already isolates clients with
schema-per-tenant (`django-tenants`, `core.Client`). We must decide where a branch sits.

## Decision
- One schema per paying client (unchanged). A new tenant app `apps.org` holds `Branch`.
- Every branch-owned model inherits an abstract `BranchOwned` (non-null `branch` FK, indexed).
- Users get branch access through role assignments (ADR-006). The active branch for a request
  comes from the `X-Branch` header (branch id), validated against the user's assignments;
  group-level users may send `X-Branch: all` for read-only consolidated views.
- `BranchScopedViewSetMixin.get_queryset()` filters by the allowed branch set and
  `perform_create()` stamps the active branch. Every module ViewSet uses it — enforced by a
  test that walks the router and fails for any branch-owned model's ViewSet without the mixin.
- Shared-across-branches data (academic years, fee heads, grade bands, pay rule sets) is
  either branch-owned with "copy from branch" or org-wide (no branch FK) — decided per model
  and listed in `decisions/dba/eraj-v1.md`.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Schema per branch, organisation in `public` | DB-enforced separation between branches | Group login across schemas, N-schema reports, cross-schema transfers; ~6–7 extra days | Doesn't fit 11 Nov; branches of one client trust each other |
| Branch as Postgres row-level security policy | DB-enforced within a schema | `SET` per request under pooling is the same failure class as search_path (FAILURE_MODES §2); hard to test | Complexity and risk for little gain at this stage |

## Consequences
### Positive
- Combined reports and transfers are plain queries; one migration run per client.
### Negative
- Branch separation is application-enforced; a missing filter leaks within one client.
### Risks
- Missed mixin → mitigated by the router-walking test and per-module cross-branch negative tests.

## Dependencies
- Depends on ADR-006 (roles per branch). Constrains every module model (ADR-002).

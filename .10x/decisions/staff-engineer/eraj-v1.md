# Staff Engineer — eraj-v1

**Date:** 2026-10-25

## Standards (apply to every module)
- Models: inherit `TimeStamped`; `SoftDelete` for master data; `BranchOwned` for branch data
  (ADR-001). No tenant FK, ever.
- Business rules live in `<app>/services.py` as keyword-only functions wrapped in
  `transaction.atomic`, taking `select_for_update` on the row being counted/limited; they raise
  `apps.core.exceptions.Conflict` (→ HTTP 409) for rule violations and call
  `apps.core.audit.record(...)`.
- Views: DRF ViewSets + router; `BranchScopedViewSetMixin`; `permission_classes=[HasPerm]` with
  `required_perms` per action; `@action` endpoints for workflow verbs (return, renew, allocate,
  approve, lock …). Pagination/filter/search/ordering via the existing DRF defaults.
- Serializers: explicit `fields`; component names unique project-wide (fixes drf-spectacular
  `Student` clash).
- Migrations: generated only; `makemigrations --check` blocking in CI.
- Money: `DecimalField(max_digits=12, decimal_places=2)`; never float.
- Dates: `timezone.localdate()` (Asia/Kolkata).
- Text shown to users: wrapped for translation (`gettext_lazy`) on the backend; message keys on
  the frontend.
- Tests: pytest + `TenantTestCase`; one test per acceptance scenario, named
  `test_scenario_<module>_<n>`; cross-branch and cross-tenant negative tests per module.
- Commits: author Abhishek Singh <abhisheksingh9135@gmail.com>; **no AI attribution lines**
  (owner instruction 2026-10-25).

## Cross-cutting reuse
`apps.core.audit.record`, `Conflict`, `TimeStamped`, `SoftDelete`, existing JWT auth, subscription
middleware, `create_tenant` command (extended to create the first Branch + Admin assignment).

# Staff Engineer — index

## [DISCOVERED] Patterns in the codebase
- Business rules in `services.py`, atomic + `select_for_update`, raise `Conflict` (409), `audit.record`.
- Abstract bases in `apps/core/mixins.py`: `TimeStamped`, `SoftDelete`.
- DRF ViewSets + routers; `RolePermission` / `IsOwner` (to be replaced by `HasPerm`, ADR-006).

| Slug | File | State |
|---|---|---|
| eraj-v1 | eraj-v1.md | Standards set 2026-10-25 |

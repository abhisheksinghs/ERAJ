# Security — eraj-v1

**Date:** 2026-10-25 · **ADRs:** 001, 004, 006

## Threat model (M1 scope)
| Threat | Control | Verified by |
|---|---|---|
| Token from client A used on client B | `schema` claim + TenantBoundJWTAuthentication | `accounts/tests/test_auth_isolation.py` (401) |
| Branch A user reads branch B data | BranchScopedViewSetMixin filters every queryset | `org/tests/test_branch_isolation.py`; router guard |
| Branch A user references branch B ids in a write | ScopedPrimaryKeyRelatedField + BranchScopedSerializer | branch isolation test (400); router guard on serializers |
| Branch spoofing via `X-Branch` | header is a choice; checked against RoleAssignment | tests (403) |
| Writes in all-branches view | `X-Branch: all` is GET-only, group admin only | tests (403) |
| Privilege escalation via unsafe @action | default deny unless `action_perms` declares it | router guard |
| Branch admin takes over another branch's user (password reset) | edit refused if user holds roles outside active branch, unless group admin | `UserManagementTest` |
| Branch admin grants group admin | `org.group_admin.assign` denied to admin | `UserManagementTest` |
| Revoked role still works until token expiry | roles read per request, not stored in JWT | design |
| JWT theft from browser JS (XSS) | tokens only in httpOnly cookies; browser calls same-origin proxy | design (ADR-004) |
| CSRF through cookie-authenticated proxy | SameSite=Lax + Origin == Host check on unsafe methods | proxy code; to test in M8 |
| Proxy path traversal to non-API backend paths | only `/api/<segments>/`; `.`/`..`/`\` rejected | proxy code |
| Tenants sharing upload folders | per-schema media storage | settings |
| Student photos publicly reachable | media not served; authenticated download views only | to implement with first file display |

## Open
- Login throttle is per IP (5/min); OTP login (M6) needs its own throttle + attempt limits.
- CSP still deferred (Next inline runtime needs nonces).
- External pen test before first paying go-live (PRODUCTION_READINESS Phase 7).

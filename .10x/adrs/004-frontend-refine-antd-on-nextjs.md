# ADR-004: Staff UI on Refine + Ant Design inside the Next.js App Router

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1
**Author:** 10x-Team (Architect + Staff Engineer); approved by Abhishek 2026-10-25

## Context
~60–70 staff screens plus a parent/student portal are needed by 2026-11-11. The current
frontend is Next.js 14.2.35 with no UI library and known critical advisories. Tokens are held
in httpOnly cookies by a Next Route Handler (BFF); that must not regress.

## Decision
- Upgrade Next.js to the current patched major (clears `npm audit` critical/high) before UI work.
- Staff UI: Refine (`@refinedev/core`, `@refinedev/antd`, `@refinedev/nextjs-router`) + Ant
  Design, with a custom data provider for DRF pagination/filters/ordering and an access-control
  provider fed by `/api/auth/me` permissions.
- All browser calls go to a same-origin Next proxy route (`/api/proxy/[...path]`) that reads
  the httpOnly cookie, attaches `Authorization: Bearer` and `X-Branch`, and forwards to the
  tenant backend. The browser never sees a JWT.
- i18n: Refine i18n provider + `en`/`hi` message files; AntD `hi_IN`/`en_US` locale switch.
- Portal: separate route group `(portal)` in the same app with a mobile-first layout.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Hand-built shadcn/ui screens | Full design control | 3–5 h per screen; misses 11 Nov | Owner chose speed |
| React-Admin | Mature | MUI-heavy, weaker Next App Router story | Refine fits Next + AntD better |
| Separate SPA (Vite) | Simple build | Loses the existing cookie BFF; tokens would reach the browser | Security regression |

## Consequences
### Positive
- List/form/filter/export screens are mostly configuration; role-based menus built in.
### Negative
- Admin-app look; framework lock-in for staff UI.
### Risks
- Refine/Next major-version incompatibility → pin exact versions that build together; CI build is blocking.

## Dependencies
- ADR-006 (permissions payload from `/api/auth/me`).

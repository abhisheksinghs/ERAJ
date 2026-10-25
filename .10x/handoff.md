# Handoff

**From:** M1 (2026-10-25) **To:** SDE — M2

- M0 + M1 done, committed and pushed. Verification: 63 Django + 23 pytest tests, `next build`,
  browser walkthrough `e2e/smoke-m1.mjs` 14/14.
- M2 order: Fees ledger first (ADR-003: FeeHead, FeePlan, Charge, Concession, gap-free Receipt,
  late fine, dues/defaulters, Tally export), then Library fines → Fees, then Hostel blocks +
  Mess (contractor, monthly + per-day, rebate, guest meals, headcount, contractor bill) +
  visitors/outpass. One test per scope-doc acceptance scenario.
- Add screens to `frontend/lib/resources.ts`; custom screens (fee collection counter) as
  their own pages under `app/(staff)/fees/…`.
- Commits: author Abhishek Singh, no AI attribution.

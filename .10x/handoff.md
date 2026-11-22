# Handoff

**From:** M5 (2026-11-22) **To:** SDE — M6 (Alerts, Portal, Learning)

- M5 built, verified and pushed. ADR-010 (transport + inventory).
  - Transport: stops with fares (own or distance slab) → monthly charges in the fees ledger; capacity
    by date; stop/change from a date; papers with expiry; GPS push `/api/transport/gps/push/`
    (X-Device-Key) + `simulate_gps`; over-speed / near-stop / paper alerts via `core.notify`
    (log-only); live map page (Leaflet/OSM); rider list PDF.
  - Inventory: ledger with weighted average cost; issue/return/damaged/lost; Admin adjustment;
    requisition approvals by amount (distinct approvers, not the requester); numbered POs + PDF;
    part/full receipts; direct purchases; reports; hostel mess cost per head.
- Verification: 182 Django tests; walkthroughs (fresh `seed_demo_tenants` each): m1 14/14,
  m2-fees 19/19, m2-hostel 12/12, m3 14/14, m3-timetable 10/10, m4 20/20, m5 21/21.
  Restart `next start` (kill port 3000) after each build.
- For M6: `apps.core.notify.guardian()` and `staff_role()` are the two call sites every module
  uses (attendance absent, fees, library, hostel outpass, transport near-stop/over-speed, inventory
  low stock, transport papers). Replace their log-only body with templates + channels + quiet
  hours + opt-out + delivery log (ADR-005); keep the signatures.
- Portal must show: transport route/stop/vehicle/driver + live bus position (`services.live`),
  fees, attendance, results, timetable, hostel outpass, homework.
- Client inputs still open: GPS provider + data access; staff → pay rule set / PF vs NPS; DLT date;
  biometric models.
- Blocker B2 (VPS + DNS) still open — staging deploy is M7.
- Commits: author Abhishek Singh, no AI attribution.

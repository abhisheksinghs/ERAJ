# Security review — M5 Transport + Inventory (2026-11-22)
See `.10x/decisions/security/m5-transport-inventory.md`. No open high findings. Medium: proxy must
overwrite X-Forwarded-For before GPS/attendance IP allow-lists are relied on (M7). `npm audit` 0
after adding Leaflet 1.9.4.

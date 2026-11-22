# Security review — M4 HR + Payroll (2026-11-22)
See `.10x/decisions/security/m4-hr-payroll.md`. No open high findings. Medium: PAN/bank numbers
not field-encrypted (rely on DB + backup encryption) — client decision under DPDP.
Dependency: Next.js bumped to 16.4.6 (7 advisories on 16.4.3).

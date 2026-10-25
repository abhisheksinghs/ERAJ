# Architect — eraj-v1

**Date:** 2026-10-25 · **ADRs:** 001–006

## Components (tenant apps unless noted)
| App | Owns | Depends on |
|---|---|---|
| core (shared) | Client, Domain, Plan, Module, Subscription, AuditLog | — |
| accounts | User, RoleAssignment, OTP login, rbac map, `/auth/me` | org |
| org | Branch, branch settings, `BranchOwned`, `BranchScopedViewSetMixin` | — |
| people | AcademicYear, Program, Term, Section, Subject, Student, Guardian, Staff, Enrollment, bulk import | org |
| fees | FeeHead, FeePlan, Charge, Concession, Receipt(+Line), Refund, ReceiptCounter, Tally export | people |
| library | Book, Category, BorrowerProfile, Issue, Fine→fees, Hold | people, fees |
| hostel | Block, Room, Allocation, Waitlist, Maintenance, Mess, MessMenu, MessEnrolment, MessLeave, GuestMeal, ContractorRate, Visitor, Outpass | people, fees |
| attendance | AttendanceRecord (daily or per lecture), Holiday, Device, Punch | people, timetable |
| exam | Exam, ExamSubject, Mark, GradeScale, result + SGPA/CGPA, report cards | people |
| hr | StaffProfile docs, LeaveType, LeaveBalance, LeaveRequest, StaffAttendance | people |
| payroll | PayRuleSet (central / Bihar), PayMatrix, DA rates, SalaryStructure, PayrollRun, Payslip, Loan, Arrears, statutory exports | hr, people |
| transport | Route, Stop, Vehicle, VehicleDocument, Assignment, GPS position | people, fees, integrations |
| inventory | Item, Vendor, Store, Requisition, Approval, PurchaseOrder, GoodsReceipt, StockMove | people |
| timetable | BellSchedule, Allocation, TimetableSlot, Substitution | people, hr |
| learning | Homework, Submission, Material, OnlineClass, Test, Question, Attempt, ClassDiary | people, timetable |
| integrations | MessageChannel/GpsSource/PunchSource providers + fakes | — |
| notify | Template (en/hi), Trigger, QuietHours, OptOut, DeliveryLog | integrations |
| portal (API) | parent/student read endpoints + requests | all above |

## Request flow
Browser → Next proxy (cookie → Bearer, X-Branch) → tenant subdomain → TenantMainMiddleware →
SubscriptionEnforcementMiddleware (module licensed?) → TenantBoundJWTAuthentication →
HasPerm (rbac) → BranchScopedViewSetMixin queryset → service function (atomic, row locks) →
AuditLog.

## Failure modes
| Failure | Effect | Guard |
|---|---|---|
| ViewSet without branch mixin | Cross-branch leak inside one client | Router-walking test; per-module negative tests |
| Action without declared permission | Unauthorised action | Default deny + router-walking test |
| Charge posted outside the business transaction | Lost or double charge | `post_charge` only inside caller's atomic block; tests |
| Receipt counter race | Duplicate/gap receipt numbers | `select_for_update` counter row; concurrency test |
| Fake provider mistaken for real | False confidence | Delivery log status `simulated`; QA report lists real vs fake |
| Payroll rule misconfiguration | Wrong salaries | Rates are data; acceptance = accountant's manual check |

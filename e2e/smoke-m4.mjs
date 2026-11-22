// M4 HR + Payroll browser walkthrough. Needs: Django on :8000 + `next start` on :3000 and fresh
// `seed_demo_tenants` data (last month's payroll locked, this month's in draft, one pending CL,
// teacher.patna linked to staff Sunita Kumari).
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m4.mjs
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");

const BASE = "http://pqr.localhost:3000";
const PW = "eraj-demo-pass-123";
const OUT = process.env.OUT ?? ".";
const results = [];
const check = (name, ok, extra = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
};
const browser = await chromium.launch();
const contexts = [];

async function login(email) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(`${BASE}/login`);
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PW);
  await Promise.all([page.waitForURL(/\/dashboard/), page.click('button[type="submit"]')]);
  await page.waitForSelector("text=Welcome", { timeout: 20000 });
  contexts.push({ page, errors });
  return { ctx, page, errors };
}
const getJson = (page, path) => page.evaluate(async (p) => (await fetch(`/api/proxy/${p}`)).json(), path);
const fetchHead = (page, url) => page.evaluate(async (u) => {
  const r = await fetch(u);
  const b = new Uint8Array(await r.arrayBuffer());
  return { status: r.status, type: r.headers.get("content-type"), head: new TextDecoder().decode(b.slice(0, 40)) };
}, url);
async function rowAction(page, rowText, actionName) {
  const row = page.locator(".ant-table-row").filter({ hasText: rowText }).first();
  await row.waitFor({ timeout: 20000 });
  const direct = row.getByRole("button", { name: actionName });
  if (await direct.count()) return direct.first().click();
  await row.locator("button").last().click(); // "more" menu
  await page.locator(".ant-dropdown:visible").getByText(actionName, { exact: true }).click();
}
const confirmModal = async (page) => page.locator(".ant-modal-confirm .ant-btn-primary, .ant-popconfirm .ant-btn-primary, .ant-modal .ant-btn-primary").last().click();
function lastWorkday() { // most recent day before today that is not a Sunday
  const d = new Date();
  do d.setDate(d.getDate() - 1); while (d.getDay() === 0);
  return d;
}
const iso = (d) => d.toLocaleDateString("en-CA");
const ym = (d) => iso(d).slice(0, 7);

try {
  // ================= HR
  const hr = await login("hr.patna@pqr.eraj.test");
  const p = hr.page;
  await p.goto(`${BASE}/hr/leave`);
  await p.waitForSelector(".ant-table-row", { timeout: 20000 });
  const menu = await p.locator(".ant-menu").first().innerText();
  const runCreate = await p.evaluate(async () => (await fetch("/api/proxy/payroll/runs", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ month: "2026-01-01" }) })).status);
  check("HR has the HR module; payroll is read-only for HR", /Leave applications/.test(menu) && runCreate === 403, `${runCreate}`);
  const pendingName = await p.locator(".ant-table-row").filter({ hasText: "Pending" }).first().locator("td").first().innerText();
  await rowAction(p, "Pending", "Approve");
  await p.waitForTimeout(1500);
  const leave = await getJson(p, "hr/leave?status=approved&page_size=50");
  check("HR approves a pending leave application", leave.results.some((a) => a.staff_name === pendingName.trim()), pendingName);
  await p.screenshot({ path: `${OUT}/m4-01-leave.png`, fullPage: true });

  const day = lastWorkday();
  await p.goto(`${BASE}/hr/mark`);
  await p.getByLabel("date").click();
  await p.getByLabel("date").fill(`${String(day.getDate()).padStart(2, "0")}-${String(day.getMonth() + 1).padStart(2, "0")}-${day.getFullYear()}`);
  await p.keyboard.press("Enter");
  await p.waitForSelector(".ant-table-row", { timeout: 20000 });
  const firstCode = (await p.locator(".ant-table-row td").first().innerText()).trim();
  await p.getByLabel(`status-${firstCode}`).getByText("Absent").click();
  await p.getByRole("button", { name: "Save attendance" }).click();
  await p.waitForSelector("text=/Saved —/", { timeout: 20000 });
  const sheet = await getJson(p, `hr/attendance/day?date=${iso(day)}`);
  check("one save marks every staff member, one absent", sheet.rows.every((r) => r.status) &&
    sheet.rows.filter((r) => r.status === "absent").length === 1, `${sheet.rows.length} staff`);
  await p.screenshot({ path: `${OUT}/m4-02-mark.png`, fullPage: true });

  await p.goto(`${BASE}/hr/reports`);
  await p.waitForSelector("text=/Working days/", { timeout: 20000 });
  const regRows = await p.locator(".ant-tabs-tabpane-active .ant-table-row").count();
  check("monthly staff register lists the staff", regRows >= 8, `${regRows}`);
  const regPdf = await fetchHead(p, `/api/proxy/hr/attendance/register?month=${ym(day)}&pdf=1`);
  check("staff register prints as PDF", regPdf.head.startsWith("%PDF"));
  await p.screenshot({ path: `${OUT}/m4-03-register.png`, fullPage: true });

  // document upload through the page
  await p.goto(`${BASE}/hr/documents`);
  const staffSelect = p.locator('.ant-select:has(.ant-select-selection-placeholder:has-text("Staff"))').first();
  await staffSelect.click();
  await p.keyboard.type("Kamla");
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "Kamla" }).first().click();
  await p.getByLabel("Title").fill("Appointment letter 2023");
  await p.setInputFiles('input[type="file"]', { name: "appointment.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF\n") });
  await p.getByRole("button", { name: "Upload" }).last().click();
  await p.waitForSelector("text=Appointment letter 2023", { timeout: 20000 });
  check("HR uploads a staff document and it is listed", true);
  await p.screenshot({ path: `${OUT}/m4-04-documents.png`, fullPage: true });

  // exit
  await p.goto(`${BASE}/hr/staff`);
  await rowAction(p, "Arjun Paswan", "Mark as left");
  await p.locator(".ant-modal:visible textarea, .ant-modal:visible input").first().fill("Contract ended");
  await p.locator(".ant-modal:visible .ant-btn-primary").click();
  await p.waitForTimeout(1500);
  const active = await getJson(p, "people/staff?search=Arjun");
  const all = await getJson(p, "hr/staff?status=all&search=Arjun");
  check("left staff drop out of active lists and stay in history", active.results.length === 0 && all.results[0]?.status === "left");

  // ================= accountant: DA revision → arrears → review → lock
  const acct = await login("accountant.patna@pqr.eraj.test");
  const a = acct.page;
  await a.goto(`${BASE}/payroll/runs`);
  await a.waitForSelector(".ant-table-row", { timeout: 20000 });
  const runs = (await getJson(a, "payroll/runs")).results;
  const draft = runs.find((r) => r.status === "draft");
  const locked = runs.find((r) => r.status === "locked");
  check("last month is locked and this month is in draft", Boolean(draft && locked));
  await a.screenshot({ path: `${OUT}/m4-05-runs.png`, fullPage: true });

  const central = (await getJson(a, "payroll/rule-sets")).results.find((r) => r.code === "central-7cpc");
  await a.goto(`${BASE}/payroll/da?rule_set=${central.id}`);
  await a.getByLabel("New DA %").fill("53");
  const pick = a.locator(".ant-picker").first();
  await pick.click();
  await a.keyboard.type(ym(new Date(locked.month)));
  await a.keyboard.press("Enter");
  await a.getByRole("button", { name: "Save revision" }).click();
  await a.waitForSelector("text=53", { timeout: 20000 });
  check("accountant revises central DA from last month", true);

  await a.goto(`${BASE}/payroll/runs`);
  await rowAction(a, "Draft", "Recalculate");
  await a.waitForTimeout(2500);
  const slips = (await getJson(a, `payroll/payslips?run=${draft.id}&page_size=50`)).results;
  const withArrears = slips.filter((s) => s.lines.some((l) => l.code === "da_arrears"));
  const biharArrears = slips.filter((s) => s.rule_set_code === "bihar-7cpc" && s.lines.some((l) => l.code === "da_arrears"));
  check("DA arrears are added for central staff only", withArrears.length === 2 && biharArrears.length === 0, `${withArrears.length} central`);

  await rowAction(a, "Draft", "Send for review");
  await a.waitForTimeout(1500);
  await rowAction(a, "In review", "Lock month");
  await confirmModal(a);
  await a.waitForTimeout(2000);
  const after = (await getJson(a, `payroll/runs/${draft.id}`));
  check("draft → review → locked", after.status === "locked", after.status);
  await a.screenshot({ path: `${OUT}/m4-06-locked.png`, fullPage: true });

  const pdf = await fetchHead(a, `/api/proxy/payroll/runs/${draft.id}/payslips`);
  check("all payslips print as one PDF", pdf.head.startsWith("%PDF"));
  const ecr = await fetchHead(a, `/api/proxy/payroll/runs/${draft.id}/ecr`);
  check("ECR file has #~# separated member lines", ecr.status === 200 && /^\d{12}#~#/.test(ecr.head), ecr.head.slice(0, 30));
  const bank = await fetchHead(a, `/api/proxy/payroll/runs/${draft.id}/bank-sheet?format=xlsx`);
  check("bank sheet downloads as Excel", bank.type?.includes("spreadsheetml") && bank.head.startsWith("PK"));
  const rev = await a.evaluate(async (id) => (await fetch(`/api/proxy/payroll/runs/${id}/reverse`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "x" }) })).status, draft.id);
  check("accountant cannot reverse a locked month", rev === 403, `${rev}`);

  await a.goto(`${BASE}/payroll/payslips?filters[0][field]=run&filters[0][operator]=eq&filters[0][value]=${draft.id}`);
  await a.waitForSelector(".ant-table-row", { timeout: 20000 });
  await a.screenshot({ path: `${OUT}/m4-07-payslips.png`, fullPage: true });

  // ================= admin reverses with a reason
  const admin = await login("owner@pqr.eraj.test");
  const ad = admin.page;
  await ad.goto(`${BASE}/payroll/runs`);
  await rowAction(ad, "Locked", "Reverse"); // newest locked month is the first row
  await ad.locator(".ant-modal:visible textarea, .ant-modal:visible input").first().fill("DA order corrected");
  await ad.locator(".ant-modal:visible .ant-btn-primary").click();
  await ad.waitForTimeout(2000);
  const reversed = await getJson(ad, `payroll/runs/${draft.id}`);
  check("Admin reverses the month with a reason", reversed.status === "reversed" && reversed.reversal_reason === "DA order corrected");

  // ================= teacher self-service
  const tch = await login("teacher.patna@pqr.eraj.test");
  const t = tch.page;
  await t.goto(`${BASE}/hr/me`);
  await t.waitForSelector("text=/CL available/", { timeout: 20000 });
  const tmenu = await t.locator(".ant-menu").first().innerText();
  check("teacher sees My leave & payslips but not Payroll", /My leave/.test(tmenu) && !/Payroll/.test(tmenu));
  await t.locator(".ant-form .ant-select").first().click();
  await t.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "ML" }).first().click();
  const range = t.locator(".ant-picker-range");
  await range.click();
  const next = new Date(); next.setDate(next.getDate() + 30); while (next.getDay() === 0) next.setDate(next.getDate() + 1);
  const d = `${String(next.getDate()).padStart(2, "0")}-${String(next.getMonth() + 1).padStart(2, "0")}-${next.getFullYear()}`;
  await range.locator("input").first().fill(d);
  await range.locator("input").last().fill(d);
  await t.getByText("Apply for leave").click(); // close the picker without submitting
  await t.getByRole("button", { name: "Apply", exact: true }).click();
  await t.waitForSelector(".ant-table-row:has-text('ML'):has-text('Pending')", { timeout: 20000 });
  check("teacher applies for medical leave and sees it pending", true);
  const mySlips = await getJson(t, "payroll/me/payslips");
  check("teacher sees own locked payslip only", mySlips.length === 1 && mySlips[0].staff_name === "Sunita Kumari", `${mySlips.length}`);
  await t.screenshot({ path: `${OUT}/m4-08-self.png`, fullPage: true });

  const allErrors = contexts.flatMap((c) => c.errors).filter((e) => !/favicon|DevTools|status of (403|404|409)/.test(e));
  check("no browser errors", allErrors.length === 0, allErrors.slice(0, 3).join(" | "));
} catch (e) {
  check("walkthrough completed", false, e.message.split("\n").slice(0, 4).join(" | "));
  for (const c of browser.contexts()) for (const pg of c.pages()) await pg.screenshot({ path: `${OUT}/fail-${Date.now()}.png`, fullPage: true }).catch(() => {});
} finally {
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}

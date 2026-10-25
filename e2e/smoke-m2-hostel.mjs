// M2 Hostel, Mess and Gate browser walkthrough. Needs: Django on :8000 + `next start` on :3000,
// fresh `seed_demo_tenants` data (blocks BH/GH, Central mess, residents PATNA-C7-001/002).
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m2-hostel.mjs
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

async function login(email) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(`${BASE}/login`);
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PW);
  await Promise.all([page.waitForURL(/\/dashboard/), page.click('button[type="submit"]')]);
  await page.waitForSelector("text=Welcome", { timeout: 20000 });
  return { ctx, page, errors };
}
const formItem = (page, label) => page.locator(".ant-form-item").filter({ hasText: label }).first();
async function pick(page, label, text, { type = true } = {}) {
  await formItem(page, label).locator(".ant-select").click();
  if (type) await page.keyboard.type(text);
  const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text }).first();
  await option.waitFor({ timeout: 10000 });
  await option.click();
}
async function save(page, urlRe) {
  await Promise.all([page.waitForURL(urlRe, { timeout: 20000 }), page.getByRole("button", { name: /save/i }).click()]);
}
// Success toasts stack over the table's action column; dismiss them before clicking there.
async function closeToasts(page) {
  for (const x of await page.locator(".ant-notification-notice-close").all()) await x.click().catch(() => {});
  await page.waitForTimeout(300);
}
const row = (page, text) => page.locator(`.ant-table-row:has-text('${text}')`).first();

try {
  const { page, errors } = await login("warden.patna@pqr.eraj.test");

  // ---- rooms: seeded blocks and rooms; full room refused
  await page.goto(`${BASE}/hostel/rooms`);
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  check("rooms list shows both blocks' rooms (6)", (await page.locator(".ant-table-row").count()) === 6);

  // ---- allocate a boy to BH-101 (1 of 2 beds taken by the seed) with the per-day mess plan
  await page.goto(`${BASE}/hostel/allocations/create`);
  await pick(page, "Student", "Student C6-1");
  await pick(page, "Room", "BH-101");
  await pick(page, "Mess plan", "Per day", { type: false });
  await save(page, /\/hostel\/allocations(\?|$)/);
  await page.waitForSelector(".ant-table-row:has-text('Student C6-1')", { timeout: 20000 });
  check("allocate a student through the form", true);
  await page.screenshot({ path: `${OUT}/m2h-01-residents.png`, fullPage: true });

  await page.goto(`${BASE}/hostel/allocations/create`);
  await pick(page, "Student", "Student C6-3");
  await pick(page, "Room", "BH-101");
  await page.getByRole("button", { name: /save/i }).click();
  await page.waitForSelector("text=/is full/", { timeout: 20000 });
  check("third student refused for a full double room", true);

  await page.goto(`${BASE}/hostel/mess-members`);
  await page.waitForSelector(".ant-table-row:has-text('Student C6-1')", { timeout: 20000 });
  check("new resident enrolled in the block's mess on the per-day plan",
    (await row(page, "Student C6-1").innerText()).includes("Per day"));

  // ---- visitor not on the approved list waits for the warden
  await page.goto(`${BASE}/hostel/visits/create`);
  await pick(page, "Visiting student", "Student C7-1");
  await page.getByLabel("Visitor name").fill("Ramesh (uncle)");
  await page.getByLabel("ID proof").fill("DL-BR01-2020");
  await save(page, /\/hostel\/visits(\?|$)/);
  await page.waitForSelector(".ant-table-row:has-text('Ramesh')", { timeout: 20000 });
  check("unlisted visitor is held", (await row(page, "Ramesh").innerText()).includes("Waiting for warden"));
  await row(page, "Ramesh").getByRole("button", { name: "Let in" }).click();
  await page.waitForSelector(".ant-table-row:has-text('Ramesh') >> text=Inside", { timeout: 20000 });
  await row(page, "Ramesh").getByRole("button", { name: "Mark left" }).click();
  await page.waitForSelector(".ant-table-row:has-text('Ramesh') >> text=Left", { timeout: 20000 });
  check("warden lets the visitor in and the log records the exit", true);

  // ---- outpass: request → approve → gate out → gate back, counted as mess leave
  const today = new Date();
  const fmt = (d) => `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
  const back = new Date(today.getTime() + 6 * 86400000);
  await page.goto(`${BASE}/hostel/outpasses/create`);
  await pick(page, "Student", "Student C7-1");
  for (const [label, d] of [["Leaving on", today], ["Returning on", back]]) {
    await formItem(page, label).locator("input").click();
    await page.keyboard.type(fmt(d));
    await page.keyboard.press("Enter");
  }
  await page.getByLabel("Reason").fill("Chhath puja");
  await pick(page, "Requested by", "Parent", { type: false });
  await save(page, /\/hostel\/outpasses(\?|$)/);
  await page.waitForSelector(".ant-table-row:has-text('Chhath puja')", { timeout: 20000 });
  for (const [btn, status] of [["Approve", "Approved"], ["Gate: out", "Out"], ["Gate: back", "Returned"]]) {
    await closeToasts(page);
    await row(page, "Chhath puja").getByRole("button", { name: btn }).click();
    await page.waitForSelector(`.ant-table-row:has-text('Chhath puja') >> text=${status}`, { timeout: 20000 });
  }
  check("outpass approved, out and back at the gate", true);
  await page.screenshot({ path: `${OUT}/m2h-02-outpass.png`, fullPage: true });
  await page.goto(`${BASE}/hostel/mess-leave`);
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  check("returned outpass appears as mess leave", (await page.locator(".ant-table-row").first().innerText()).includes("Chhath puja"));

  // ---- menu prints as a PDF
  await page.goto(`${BASE}/hostel/messes`);
  await page.waitForSelector(".ant-table-row:has-text('Central mess')", { timeout: 20000 });
  const [req] = await Promise.all([
    page.context().waitForEvent("request", { predicate: (r) => r.url().includes("menu-pdf"), timeout: 20000 }),
    row(page, "Central mess").getByRole("button", { name: "Print menu" }).click(),
  ]);
  const magic = await page.evaluate(async (u) => new TextDecoder().decode((await (await fetch(u)).arrayBuffer()).slice(0, 4)), req.url());
  check("weekly menu prints as PDF", magic === "%PDF");

  // ---- mess form round-trips blocks and contractor rates
  await page.goto(`${BASE}/hostel/messes`);
  await row(page, "Central mess").locator("button.ant-btn-icon-only").first().click();
  await page.waitForURL(/\/edit/, { timeout: 20000 });
  await page.waitForSelector("text=Boys hostel", { timeout: 20000 });
  const rates = await page.locator('input[id^="meal_rates_"][id$="_rate"]').count();
  check("mess edit form shows served blocks and 4 contractor rates", rates === 4, `${rates} rates`);

  // ---- accountant sees the hostel + mess charges on the resident's fee account
  const acc = await login("accountant.patna@pqr.eraj.test");
  await acc.page.goto(`${BASE}/fees/accounts`);
  await acc.page.waitForSelector(".ant-table-row", { timeout: 20000 });
  await row(acc.page, "PATNA-C6-001").getByRole("button", { name: "Collect" }).click();
  await acc.page.waitForSelector("text=Student C6-1 ·", { timeout: 20000 });
  const dues = await acc.page.locator(".ant-card:has(.ant-card-head-title:text-is('Dues'))").innerText();
  check("hostel fee is on the resident's fee account", /Hostel BH-101/.test(dues));
  await acc.page.screenshot({ path: `${OUT}/m2h-03-fee-account.png`, fullPage: true });
  await acc.ctx.close();

  const allErrors = [...errors, ...acc.errors].filter((e) => !/favicon|Download the React DevTools|status of 409/.test(e));
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

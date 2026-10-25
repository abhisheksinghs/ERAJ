// M3 Attendance + Exam browser walkthrough. Needs: Django on :8000 + `next start` on :3000,
// fresh `seed_demo_tenants` data (teacher.patna = class teacher of Class 6-A and 7-A, teaches Maths).
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m3.mjs
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
async function choose(page, selectLocator, text, { type = true } = {}) {
  // dependent selects stay disabled until their parent choice has loaded
  await selectLocator.and(page.locator(".ant-select:not(.ant-select-disabled)")).waitFor({ timeout: 15000 });
  await selectLocator.click();
  if (type) await page.keyboard.type(text);
  const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text }).first();
  await option.waitFor({ timeout: 10000 });
  await option.click();
}
const selectWith = (page, placeholder) => page.locator(`.ant-select:has(.ant-select-selection-placeholder:has-text("${placeholder}"))`).first();
// The most recent weekday before today (seeded attendance exists for it).
function lastWeekday() {
  const d = new Date();
  do d.setDate(d.getDate() - 1); while (d.getDay() === 0);
  return d;
}
const fmt = (d) => `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;

try {
  // ================= teacher: attendance
  const { page, errors } = await login("teacher.patna@pqr.eraj.test");
  await page.goto(`${BASE}/attendance/mark`);
  await choose(page, page.getByLabel("section").locator("xpath=ancestor::div[contains(@class,'ant-select')]").first(), "Class 6-A", { type: false });
  const today = new Date();
  if (today.getDay() === 0) {
    await page.waitForSelector("text=/Holiday: Sunday/", { timeout: 20000 });
    check("today (Sunday) is shown as a holiday, not markable", true);
  }
  // past weekday already marked by the seed: teacher change is refused
  const past = lastWeekday();
  await page.getByLabel("date").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(fmt(past));
  await page.keyboard.press("Enter");
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  const rows = await page.locator(".ant-table-row").count();
  check("sheet lists the section's 5 students with saved marks", rows === 5, `${rows}`);
  await page.screenshot({ path: `${OUT}/m3-01-mark.png`, fullPage: true });
  const first = page.locator(".ant-table-row").first();
  const wasAbsent = (await first.getAttribute("style") ?? "").includes("255, 241, 240");
  await first.locator("td").nth(1).click(); // tap toggles present ↔ absent
  await page.getByRole("button", { name: "Save attendance" }).click();
  const refused = await page.waitForSelector("text=/only be corrected by Admin/", { timeout: 20000 }).then(() => true).catch(() => false);
  check("teacher's change to a past day is refused", refused, wasAbsent ? "was absent" : "was present");

  // ================= teacher: marks
  await page.goto(`${BASE}/exam/marks`);
  await choose(page, selectWith(page, "Exam"), "Class 6");
  await choose(page, selectWith(page, "Subject"), "Mathematics", { type: false });
  await choose(page, selectWith(page, "Section"), "Class 6-A", { type: false });
  await page.waitForSelector("text=/Theory \\/80/", { timeout: 20000 });
  const theory = page.locator('input[aria-label^="theory-"]').first();
  await theory.fill("77");
  await page.getByRole("button", { name: "Save marks" }).click();
  await page.waitForSelector("text=/Done: 5/", { timeout: 20000 });
  check("maths teacher saves Maths marks for Class 6-A", true);
  await page.screenshot({ path: `${OUT}/m3-02-marks.png`, fullPage: true });

  await choose(page, page.locator(".ant-select").filter({ hasText: "Mathematics" }).first(), "Science", { type: false });
  const denied = await page.waitForSelector("text=/only for the subjects you teach/", { timeout: 20000 }).then(() => true).catch(() => false);
  check("the same teacher cannot open Science marks", denied);

  await choose(page, page.locator(".ant-select").filter({ hasText: "Science" }).first(), "Mathematics", { type: false });
  await page.getByRole("button", { name: "Lock section" }).click();
  await page.getByRole("button", { name: "OK" }).click();
  await page.waitForSelector("text=/Marks are locked/", { timeout: 20000 });
  check("class teacher locks the section; grid becomes read-only", await page.getByRole("button", { name: "Save marks" }).count() === 0);

  // ================= admin: results + reports
  const admin = await login("owner@pqr.eraj.test");
  const p = admin.page;
  await p.goto(`${BASE}/exam/results`);
  await choose(p, selectWith(p, "Exam"), "Class 6");
  await p.waitForSelector(".ant-table-row", { timeout: 20000 });
  const resRows = await p.locator(".ant-table-row").count();
  check("results list the class with ranks", resRows === 5, `${resRows} rows`);
  await p.screenshot({ path: `${OUT}/m3-03-results.png`, fullPage: true });
  await choose(p, selectWith(p, "Section (all if blank)"), "Class 6-A", { type: false });
  const cardsHref = await p.getByRole("link", { name: /Print report cards/ }).getAttribute("href");
  const magic = await p.evaluate(async (u) => new TextDecoder().decode((await (await fetch(u)).arrayBuffer()).slice(0, 4)), cardsHref);
  check("class report cards print as one PDF", magic === "%PDF");
  await p.getByRole("tab", { name: "Analysis" }).click();
  await p.waitForSelector("text=Toppers", { timeout: 20000 });
  check("analysis shows subject table and toppers", (await p.locator(".ant-tabs-tabpane-active .ant-table-row").count()) >= 4);

  await p.goto(`${BASE}/exam/marks`);
  await choose(p, selectWith(p, "Exam"), "Class 6");
  await choose(p, selectWith(p, "Subject"), "Mathematics", { type: false });
  await choose(p, selectWith(p, "Section"), "Class 6-A", { type: false });
  await p.getByRole("button", { name: "Unlock" }).click();
  await p.locator(".ant-modal textarea").fill("Re-check Q4 marks");
  await p.locator(".ant-modal .ant-btn-primary").click();
  await p.waitForSelector("button:has-text('Save marks')", { timeout: 20000 });
  check("admin unlocks with a reason", true);

  await p.goto(`${BASE}/attendance/reports`);
  await choose(p, selectWith(p, "Section"), "Class 6-A", { type: false });
  await p.waitForSelector("text=/Working days/", { timeout: 20000 });
  const regRows = await p.locator(".ant-tabs-tabpane-active .ant-table-row").count();
  check("monthly register shows the section", regRows === 5, `${regRows}`);
  await p.screenshot({ path: `${OUT}/m3-04-register.png`, fullPage: true });
  const regHref = await p.getByRole("link", { name: /Print/ }).first().getAttribute("href");
  const regMagic = await p.evaluate(async (u) => new TextDecoder().decode((await (await fetch(u)).arrayBuffer()).slice(0, 4)), regHref);
  check("register prints as PDF", regMagic === "%PDF");
  await p.getByRole("tab", { name: "Below minimum %" }).click();
  await p.waitForTimeout(1500);
  const belowRows = await p.locator(".ant-tabs-tabpane-active .ant-table-row").count();
  check("below-75% list finds the seeded low-attendance students", belowRows >= 1, `${belowRows}`);

  const allErrors = [...errors, ...admin.errors].filter((e) => !/favicon|DevTools|status of (403|409)/.test(e));
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

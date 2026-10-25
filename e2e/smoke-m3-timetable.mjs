// M3 Timetable browser walkthrough. Needs: Django on :8000 + `next start` on :3000, fresh `seed_demo_tenants`.
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m3-timetable.mjs
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
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
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
  await selectLocator.and(page.locator(".ant-select:not(.ant-select-disabled)")).waitFor({ timeout: 15000 });
  await selectLocator.click();
  if (type) await page.keyboard.type(text);
  const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text }).first();
  await option.waitFor({ timeout: 10000 });
  await option.click();
}
const selectWith = (page, placeholder) => page.locator(`.ant-select:has(.ant-select-selection-placeholder:has-text("${placeholder}"))`).first();
const pdfMagic = (page, href) => page.evaluate(async (u) => new TextDecoder().decode((await (await fetch(u)).arrayBuffer()).slice(0, 4)), href);
function nextMonday() {
  const d = new Date();
  do d.setDate(d.getDate() + 1); while (d.getDay() !== 1);
  return d;
}
const fmt = (d) => `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;

try {
  const { page, errors } = await login("owner@pqr.eraj.test");

  // ---- view + print
  await page.goto(`${BASE}/timetable/view`);
  await choose(page, selectWith(page, "Section"), "Class 6-A", { type: false });
  await page.waitForSelector(".tt-grid", { timeout: 20000 });
  const filled = await page.locator(".tt-grid td[data-cell] div[style]").count();
  check("section timetable shows the week", filled >= 30, `${filled} periods`);
  await page.screenshot({ path: `${OUT}/m3t-01-section.png`, fullPage: true });
  await page.getByText("Teacher", { exact: true }).click();
  await choose(page, selectWith(page, "Teacher"), "Sunita");
  await page.waitForSelector(".tt-grid", { timeout: 20000 });
  const href = await page.getByRole("link", { name: /Print/ }).getAttribute("href");
  check("teacher-wise timetable prints as PDF", (await pdfMagic(page, href)) === "%PDF");

  // ---- builder: free Monday P1 of Class 7-A, then try Sunita (busy in 6-A at that time)
  await page.goto(`${BASE}/timetable/builder`);
  await choose(page, selectWith(page, "Section"), "Class 7-A", { type: false });
  await page.waitForSelector(".tt-grid", { timeout: 20000 });
  const cell = page.locator('td[data-cell]').first();
  if (await cell.getByRole("button", { name: "remove period" }).count()) {
    await cell.getByRole("button", { name: "remove period" }).click();
    await page.getByRole("button", { name: "OK" }).click();
    await cell.getByRole("button", { name: /add Monday/ }).waitFor({ timeout: 20000 });
  }
  await cell.getByRole("button", { name: /add Monday/ }).click();
  await choose(page, page.locator(".ant-modal .ant-select").first(), "Sunita", { type: false });
  await page.locator(".ant-modal .ant-btn-primary").click();
  const refused = await page.waitForSelector("text=/Sunita Kumari already teaches Class 6-A in Period 1/", { timeout: 20000 }).then(() => true).catch(() => false);
  check("placing a teacher already teaching in that period is refused", refused);
  await page.screenshot({ path: `${OUT}/m3t-02-clash.png` });
  await choose(page, page.locator(".ant-modal .ant-select").first(), "Pooja", { type: false });
  await page.locator(".ant-modal .ant-btn-primary").click();
  await page.waitForSelector(".ant-modal", { state: "detached", timeout: 20000 }).catch(() => {});
  check("a free teacher is placed instead", (await cell.innerText()).includes("Pooja"), (await cell.innerText()).replace(/\n/g, " "));

  // ---- substitution: Sunita away next Monday
  const monday = nextMonday();
  await page.goto(`${BASE}/timetable/substitution`);
  await page.getByLabel("date").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(fmt(monday));
  await page.keyboard.press("Enter");
  await choose(page, selectWith(page, "Mark a teacher away"), "Sunita");
  await page.getByPlaceholder("Reason").fill("Casual leave");
  await page.getByRole("button", { name: "Mark a teacher away" }).click();
  await page.waitForSelector(".ant-tag:has-text('Sunita Kumari')", { timeout: 20000 });
  await page.waitForSelector("button:has-text('Confirm')", { timeout: 20000 });
  const toCover = await page.locator(".ant-card:has-text('Periods to cover') .ant-table-row").count();
  check("absent teacher's periods are listed with suggested substitutes", toCover >= 2, `${toCover} periods`);
  await page.screenshot({ path: `${OUT}/m3t-03-cover.png`, fullPage: true });
  for (let i = 0; i < toCover; i++) {
    const btn = page.getByRole("button", { name: "Confirm" }).first();
    if (!(await btn.count())) break;
    await btn.click();
    await page.waitForTimeout(800);
  }
  const confirmed = await page.locator(".ant-card:has-text('Periods to cover') .ant-tag-green").count();
  check("every period gets a confirmed substitute", confirmed === toCover, `${confirmed}/${toCover}`);
  await page.getByRole("tab", { name: "Monthly register" }).click();
  const regHref = await page.getByRole("link", { name: /Print/ }).getAttribute("href");
  check("substitution register prints as PDF", (await pdfMagic(page, regHref)) === "%PDF");

  // ---- a teacher can view but not build
  const teacher = await login("teacher.patna@pqr.eraj.test");
  await teacher.page.goto(`${BASE}/timetable/builder`);
  await teacher.page.waitForSelector("text=Your role does not include this screen.", { timeout: 20000 });
  check("teacher cannot open the builder", true);
  await teacher.page.goto(`${BASE}/timetable/view`);
  await choose(teacher.page, selectWith(teacher.page, "Section"), "Class 6-A", { type: false });
  await teacher.page.waitForSelector(".tt-grid", { timeout: 20000 });
  check("teacher can view the timetable", true);

  const allErrors = [...errors, ...teacher.errors].filter((e) => !/favicon|DevTools|status of (403|409)/.test(e));
  check("no browser errors", allErrors.length === 0, allErrors.slice(0, 3).join(" | "));
} catch (e) {
  check("walkthrough completed", false, e.message.split("\n").slice(0, 3).join(" | "));
  for (const c of browser.contexts()) for (const pg of c.pages()) await pg.screenshot({ path: `${OUT}/fail-${Date.now()}.png`, fullPage: true }).catch(() => {});
} finally {
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}

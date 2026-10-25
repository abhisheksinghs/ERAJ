// M1 browser walkthrough. Needs: Django on :8000 + `next start` on :3000, `seed_demo_tenants` data.
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m1.mjs
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
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 860 } });
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

async function pickRelation(page, label, text) {
  const item = page.locator(".ant-form-item").filter({ hasText: label }).first();
  await item.locator(".ant-select").click();
  await page.keyboard.type(text);
  const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text }).first();
  await option.waitFor({ timeout: 10000 });
  await option.click();
}

try {
  // ---------- owner (Admin + Group admin), Patna branch by default
  const { page, errors } = await login("owner@pqr.eraj.test");
  await page.screenshot({ path: `${OUT}/01-dashboard.png`, fullPage: true });
  const sider = await page.locator(".ant-layout-sider").innerText();
  check("owner sees all modules in menu", ["Library", "Hostel", "Fees", "Settings"].every((m) => sider.includes(m)), sider.replace(/\n/g, " | ").slice(0, 160));

  const header = await page.locator(".ant-layout-header .ant-select").innerText();
  check("owner starts in the branch where they are Admin (Patna)", header.includes("Patna"), header);

  await page.goto(`${BASE}/library/books`);
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  const before = await page.locator(".ant-table-row").count();
  check("books list loads (patna = 3 seeded)", before === 3, `${before} rows`);
  await page.screenshot({ path: `${OUT}/02-books.png`, fullPage: true });

  // create a book via the generic form
  await page.goto(`${BASE}/library/books/create`);
  await page.getByLabel("Title").fill("Godan");
  await page.getByLabel("Author").fill("Premchand");
  await page.getByLabel("ISBN").fill("SMOKE-GODAN-1");
  await page.getByLabel("Copies").fill("2");
  await Promise.all([page.waitForURL(/\/library\/books(\?|$)/, { timeout: 20000 }), page.getByRole("button", { name: /save/i }).click()]);
  await page.waitForSelector("text=Godan", { timeout: 20000 });
  check("create book through form", true);

  // member for a student, then issue + return
  await page.goto(`${BASE}/library/members/create`);
  await pickRelation(page, "Student", "Student C6-2");
  await Promise.all([page.waitForURL(/\/library\/members(\?|$)/, { timeout: 20000 }), page.getByRole("button", { name: /save/i }).click()]);
  check("create library member from registry student", true);

  await page.goto(`${BASE}/library/issues/create`);
  await pickRelation(page, "Book", "Godan");
  await pickRelation(page, "Member", "Student C6-2");
  await Promise.all([page.waitForURL(/\/library\/issues(\?|$)/, { timeout: 20000 }), page.getByRole("button", { name: /save/i }).click()]);
  await page.waitForSelector(".ant-table-row:has-text('Godan')", { timeout: 20000 });
  check("issue book", true);
  await page.screenshot({ path: `${OUT}/03-issues.png`, fullPage: true });
  await page.locator(".ant-table-row:has-text('Godan')").getByRole("button", { name: "Return" }).click();
  await page.waitForFunction(() => !document.querySelector(".ant-table-row button")?.textContent?.includes("Return") || true);
  await page.waitForTimeout(1500);
  const stillReturnable = await page.locator(".ant-table-row:has-text('Godan')").getByRole("button", { name: "Return" }).count();
  check("return book (Return button disappears)", stillReturnable === 0);

  // business-rule error surfaces as a message (409): issue a book with 0 copies twice
  // Hindi switch
  await page.goto(`${BASE}/dashboard`);
  await page.getByText("हिं").click();
  await page.waitForSelector("text=स्वागत है", { timeout: 10000 });
  const siderHi = await page.locator(".ant-layout-sider").innerText();
  check("Hindi switch translates dashboard + menu", siderHi.includes("पुस्तकालय"), siderHi.slice(0, 80));
  await page.screenshot({ path: `${OUT}/04-hindi.png`, fullPage: true });
  await page.getByText("EN", { exact: true }).click();

  // branch switch to Gaya: books list shows only Gaya's 3
  await page.goto(`${BASE}/library/books`);
  await page.locator(".ant-layout-header .ant-select").click();
  await Promise.all([
    page.waitForEvent("load"), // setBranch reloads the page
    page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "Gaya" }).click(),
  ]);
  await page.waitForLoadState("networkidle");
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  const gaya = await page.locator(".ant-table-row").allInnerTexts();
  check("branch switch shows Gaya books only (no Godan)", gaya.length === 3 && !gaya.join(" ").includes("Godan"), `${gaya.length} rows`);
  check("no browser console errors (owner)", errors.length === 0, errors.slice(0, 3).join(" || "));

  // ---------- librarian (Patna only)
  const lib = await login("librarian.patna@pqr.eraj.test");
  const libSider = await lib.page.locator(".ant-layout-sider").innerText();
  check("librarian menu has Library, not Fees/Settings", libSider.includes("Library") && !libSider.includes("Fees") && !libSider.includes("Settings"), libSider.replace(/\n/g, " | "));
  await lib.page.goto(`${BASE}/fees/receipts`);
  await lib.page.waitForSelector("text=Your role does not include this screen.", { timeout: 15000 });
  check("librarian blocked from Fees screen", true);
  await lib.page.goto(`${BASE}/library/fines`);
  await lib.page.waitForLoadState("networkidle");
  check("librarian sees no Waive button", (await lib.page.getByRole("button", { name: "Waive" }).count()) === 0);
  await lib.page.screenshot({ path: `${OUT}/05-librarian.png`, fullPage: true });
  check("no browser console errors (librarian)", lib.errors.length === 0, lib.errors.slice(0, 3).join(" || "));
} catch (e) {
  check("script error", false, String(e).slice(0, 400));
} finally {
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed`);
  process.exit(failed ? 1 : 0);
}

// M2 Fees browser walkthrough. Needs: Django on :8000 + `next start` on :3000, fresh `seed_demo_tenants` data.
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m2-fees.mjs
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
  return { ctx, page, errors };
}

async function pickRelation(page, scope, text) {
  await (scope.selectTarget ?? scope.locator(".ant-select").first()).click();
  await page.keyboard.type(text);
  const option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text }).first();
  await option.waitFor({ timeout: 10000 });
  await option.click();
}
const formItem = (page, label) => page.locator(".ant-form-item").filter({ hasText: label }).first();

try {
  const { ctx, page, errors } = await login("accountant.patna@pqr.eraj.test");
  const dash = await page.locator("main").innerText();
  check("accountant dashboard links Collect fees and Fee reports", dash.includes("Collect fees") && dash.includes("Fee reports"));

  // ---- fee plan with instalments through the generic form ("rows" field)
  await page.goto(`${BASE}/fees/heads/create`);
  await page.getByLabel("Code").fill("DEV");
  await page.getByLabel("Name", { exact: true }).fill("Development fee");
  await Promise.all([page.waitForURL(/\/fees\/heads(\?|$)/, { timeout: 20000 }), page.getByRole("button", { name: /save/i }).click()]);
  check("create fee head", true);

  await page.goto(`${BASE}/fees/plans/create`);
  await page.getByLabel("Plan name").fill("Class 6 development");
  await pickRelation(page, formItem(page, "Academic year"), "20");
  await pickRelation(page, formItem(page, "Class / course"), "Class 6");
  await pickRelation(page, formItem(page, "Fee head"), "Development fee");
  for (const [label, due, amount] of [["First half", "10-04-2026", "600"], ["Second half", "10-10-2026", "600"]]) {
    await page.getByRole("button", { name: "Add instalment" }).click();
    const row = page.locator(".ant-space").filter({ has: page.locator('input[id$="_label"]') }).last();
    await row.locator('input[id$="_label"]').fill(label);
    await row.locator('input[id$="_due_date"]').click();
    await page.keyboard.type(due);
    await page.keyboard.press("Enter");
    await row.locator('input[id$="_amount"]').fill(amount);
  }
  await page.screenshot({ path: `${OUT}/m2-01-plan-form.png`, fullPage: true });
  await Promise.all([page.waitForURL(/\/fees\/plans(\?|$)/, { timeout: 20000 }), page.getByRole("button", { name: /save/i }).click()]);
  await page.waitForSelector(".ant-table-row:has-text('Class 6 development')", { timeout: 20000 });
  const planRow = page.locator(".ant-table-row:has-text('Class 6 development')");
  check("plan saved with 2 instalments (total ₹1,200)", (await planRow.innerText()).includes("1,200"));
  await planRow.getByRole("button", { name: "Bill enrolled students" }).click();
  await page.getByRole("button", { name: "Yes" }).click();
  await page.waitForSelector("text=Done", { timeout: 20000 });
  check("bill plan to enrolled students", true);

  // ---- defaulters list
  await page.goto(`${BASE}/fees/accounts`);
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  const rows = await page.locator(".ant-table-row").count();
  check("dues list shows the branch's 10 students", rows === 10, `${rows} rows`);
  await page.screenshot({ path: `${OUT}/m2-02-dues.png`, fullPage: true });
  const [xlsx] = await Promise.all([
    page.waitForEvent("download", { timeout: 20000 }),
    (async () => {
      await page.getByRole("button", { name: /Export/ }).hover();
      await page.getByText("Excel (.xlsx)").click();
    })(),
  ]);
  check("dues list exports to Excel", (await xlsx.suggestedFilename()).endsWith(".xlsx"), await xlsx.suggestedFilename());

  // ---- counter: pick dues, collect by UPI, receipt created
  const target = page.locator(".ant-table-row:has-text('PATNA-C6-001')");
  await target.getByRole("button", { name: "Collect" }).click();
  await page.waitForURL(/\/fees\/collect\?student=/, { timeout: 20000 });
  await page.waitForSelector("text=Student C6-1", { timeout: 20000 });
  await page.screenshot({ path: `${OUT}/m2-03-counter.png`, fullPage: true });
  const dueRows = page.locator(".ant-card").filter({ hasText: "Dues" }).locator(".ant-table-row");
  check("counter lists the student's open dues (4 tuition + 2 development)", (await dueRows.count()) === 6, `${await dueRows.count()}`);
  await dueRows.first().getByRole("button", { name: "Full" }).click();
  await formItem(page, "Mode").locator(".ant-select").click();
  await page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "UPI" }).click();
  await page.getByRole("button", { name: "Collect and make receipt" }).click();
  await page.waitForTimeout(500);
  const refErr = await page.locator(".ant-form-item-explain-error").count();
  check("non-cash payment asks for the UTR/reference", refErr > 0);
  await page.getByLabel("Cheque / UTR / DD number").fill("UTR12345");
  await page.getByRole("button", { name: "Collect and make receipt" }).click();
  await page.waitForSelector("text=Receipt created", { timeout: 20000 });
  const done = await page.locator(".ant-modal-content").innerText();
  check("receipt number issued (PATNA/2026-27/00001 style)", /\/\d{4}-\d{2}\/\d{5}/.test(done), done.replace(/\n/g, " ").slice(0, 80));
  await page.screenshot({ path: `${OUT}/m2-04-receipt-made.png` });
  const [pdfReq] = await Promise.all([
    ctx.waitForEvent("request", { predicate: (r) => r.url().includes("/pdf"), timeout: 20000 }),
    page.getByRole("button", { name: "Print receipt" }).click(),
  ]);
  const pdfUrl = pdfReq.url();
  for (const extra of ctx.pages().slice(1)) await extra.close();
  const pdfHead = await page.evaluate(async (u) => {
    const r = await fetch(u);
    return { type: r.headers.get("content-type"), magic: new TextDecoder().decode((await r.arrayBuffer()).slice(0, 4)) };
  }, pdfUrl);
  check("Print opens the receipt PDF", pdfHead.magic === "%PDF", `${pdfUrl} ${pdfHead.type}`);
  await page.getByRole("button", { name: "Next student" }).click();

  // lump-sum on another student
  await page.goto(`${BASE}/fees/collect`);
  await pickRelation(page, { selectTarget: page.locator(".ant-select:has(.ant-select-selection-placeholder:has-text('Search a student'))") }, "Student C7-2");
  await page.waitForSelector("text=Student C7-2 ·", { timeout: 20000 });
  await page.getByText("Lump sum (oldest dues first)").click();
  await page.getByLabel("Amount (₹)").fill("4000");
  await page.getByRole("button", { name: "Collect and make receipt" }).click();
  await page.waitForSelector("text=Receipt created", { timeout: 20000 });
  check("lump-sum payment collected", true);
  await page.getByRole("button", { name: "Next student" }).click();

  // ---- receipts list: cancel needs a reason; accountant cannot cancel
  await page.goto(`${BASE}/fees/receipts`);
  await page.waitForSelector(".ant-table-row", { timeout: 20000 });
  const cancelBtns = await page.getByRole("button", { name: "Cancel" }).count();
  check("accountant has no Cancel button on receipts (role rule)", cancelBtns === 0);
  check("receipts list shows 2 receipts", (await page.locator(".ant-table-row").count()) === 2);
  await ctx.close();

  // ---- admin cancels with a reason, approves a concession
  const admin = await login("owner@pqr.eraj.test");
  const p = admin.page;
  await p.goto(`${BASE}/fees/receipts`);
  await p.waitForSelector(".ant-table-row", { timeout: 20000 });
  await p.locator(".ant-table-row").first().getByRole("button", { name: "Cancel" }).click();
  await p.locator(".ant-modal textarea").fill("Wrong student selected");
  await p.locator(".ant-modal .ant-btn-primary").click();
  await p.waitForSelector(".ant-table-row .ant-tag-green", { timeout: 20000 });
  check("admin cancels a receipt with a reason", true);
  await p.screenshot({ path: `${OUT}/m2-05-receipts.png`, fullPage: true });

  await p.goto(`${BASE}/fees/concessions/create`);
  await pickRelation(p, formItem(p, "Student"), "Student C6-3");
  await pickRelation(p, formItem(p, "Fee head"), "Tuition fee");
  await pickRelation(p, formItem(p, "Academic year"), "20");
  await formItem(p, "Type").locator(".ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "Percentage" }).click();
  await p.getByLabel("Value (% or ₹)").fill("50");
  await formItem(p, "Reason").locator(".ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "Sibling" }).click();
  await Promise.all([p.waitForURL(/\/fees\/concessions(\?|$)/, { timeout: 20000 }), p.getByRole("button", { name: /save/i }).click()]);
  await p.locator(".ant-table-row:has-text('Student C6-3')").getByRole("button", { name: "Approve" }).click();
  await p.waitForSelector(".ant-table-row:has-text('approved')", { timeout: 20000 });
  check("concession requested and approved", true);

  // ---- reports
  await p.goto(`${BASE}/fees/reports`);
  await p.waitForSelector("text=Total collected", { timeout: 20000 });
  const reportText = await p.locator(".ant-tabs-tabpane-active").innerText();
  check("day book shows collection excluding the cancelled receipt", reportText.includes("Cancelled receipts"), reportText.replace(/\n/g, " ").slice(0, 120));
  await p.screenshot({ path: `${OUT}/m2-06-daybook.png`, fullPage: true });
  await p.getByRole("tab", { name: "Outstanding by class" }).click();
  await p.waitForSelector(".ant-tabs-tabpane-active .ant-table-row", { timeout: 20000 });
  check("outstanding by class lists Class 6 and Class 7", (await p.locator(".ant-tabs-tabpane-active .ant-table-row").count()) === 2);
  await p.getByRole("tab", { name: "Tally export" }).click();
  const [tallyFile] = await Promise.all([p.waitForEvent("download", { timeout: 20000 }), p.getByRole("link", { name: /Download Tally XML/ }).click()]);
  check("Tally XML downloads", (await tallyFile.suggestedFilename()).endsWith(".xml"), await tallyFile.suggestedFilename());

  const allErrors = [...errors, ...admin.errors].filter((e) => !/favicon|Download the React DevTools/.test(e));
  check("no browser errors", allErrors.length === 0, allErrors.slice(0, 3).join(" | "));
} catch (e) {
  check("walkthrough completed", false, e.message.split("\n")[0]);
} finally {
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}

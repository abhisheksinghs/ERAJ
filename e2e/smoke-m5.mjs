// M5 Transport + Inventory browser walkthrough. Needs: Django on :8000 + `next start` on :3000 and fresh
// `seed_demo_tenants` data (routes R1/R2 with riders, bus insurance due in 20 days, recent GPS positions;
// stores, stock, a ₹60,000 requisition awaiting approval, an order partly received).
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m5.mjs
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
  contexts.push({ page, errors });
  return { ctx, page, errors };
}
const getJson = (page, path) => page.evaluate(async (p) => (await fetch(`/api/proxy/${p}`)).json(), path);
const postJson = (page, path, body) => page.evaluate(async ([p, b]) => {
  const r = await fetch(`/api/proxy/${p}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
  return { status: r.status, body: await r.json().catch(() => null) };
}, [path, body]);
const head = (page, url) => page.evaluate(async (u) => {
  const r = await fetch(u);
  return { status: r.status, type: r.headers.get("content-type"), head: new TextDecoder().decode(new Uint8Array(await r.arrayBuffer()).slice(0, 8)) };
}, url);
async function pick(page, placeholder, text) {
  const sel = page.locator(`.ant-select:has(.ant-select-selection-placeholder:has-text("${placeholder}"))`).first();
  await sel.and(page.locator(".ant-select:not(.ant-select-disabled)")).waitFor({ timeout: 15000 });
  await sel.click();
  if (text) await page.keyboard.type(text);
  const opt = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text ?? "" }).first();
  await opt.waitFor({ timeout: 10000 });
  await opt.click();
}
async function pickId(page, id, text) {
  const sel = page.locator(`#${id}`).locator("xpath=ancestor::div[contains(@class,'ant-select')][1]");
  await sel.click();
  await page.keyboard.type(text);
  const opt = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: text }).first();
  await opt.waitFor({ timeout: 10000 });
  await opt.click();
}
const patchJson = (page, path, body) => page.evaluate(async ([p, b]) => (await fetch(`/api/proxy/${p}`, {
  method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).status, [path, body]);
async function rowAction(page, rowText, actionName) {
  const row = page.locator(".ant-table-row").filter({ hasText: rowText }).first();
  await row.waitFor({ timeout: 20000 });
  const direct = row.getByRole("button", { name: actionName });
  if (await direct.count()) return direct.first().click();
  await row.locator("button").last().click();
  await page.locator(".ant-dropdown:visible").getByText(actionName, { exact: true }).click();
}
const confirm = (page) => page.locator(".ant-modal-confirm .ant-btn-primary, .ant-popconfirm .ant-btn-primary, .ant-modal .ant-btn-primary").last().click();

try {
  // ================= transport in-charge
  const tr = await login("transport.patna@pqr.eraj.test");
  const p = tr.page;
  await p.goto(`${BASE}/transport/live`);
  await p.waitForSelector(".ant-table-row", { timeout: 20000 });
  await p.waitForSelector(".leaflet-container", { timeout: 20000 });
  const markers = await p.locator(".leaflet-interactive").count();
  const live = await getJson(p, "transport/reports/live");
  check("live map shows both vehicles with a fresh GPS position", markers >= 2 && live.every((v) => v.age_seconds !== null && v.age_seconds < 600),
    live.map((v) => `${v.registration_no}:${v.age_seconds}s`).join(" "));
  await p.locator(".ant-table-row").first().click();
  await p.waitForTimeout(1500);
  check("clicking a vehicle draws its trip", (await p.locator("path.leaflet-interactive").count()) >= 1);
  await p.screenshot({ path: `${OUT}/m5-01-live.png`, fullPage: true });

  // assign a new student to stop 3 of R1
  const before = (await getJson(p, "transport/assignments?page_size=100")).count;
  const free = (await getJson(p, "people/students?page_size=100")).results.map((s) => s.full_name);
  const riding = new Set((await getJson(p, "transport/assignments?page_size=100")).results.map((a) => a.rider_name));
  const newcomer = free.find((n) => !riding.has(n));
  await p.goto(`${BASE}/transport/assign`);
  await pick(p, "Student", newcomer.split(" ").pop());
  await pick(p, "Route", "R1");
  await pick(p, "Stop", "3.");
  await pick(p, "Vehicle", "BR01PA");
  await p.getByRole("button", { name: "Save" }).click();
  await p.waitForURL(/\/transport\/assignments/, { timeout: 20000 });
  const after = await getJson(p, "transport/assignments?page_size=100");
  const mine = after.results.find((a) => a.rider_name === newcomer);
  check("in-charge assigns a student to stop 3", after.count === before + 1 && mine?.stop_name === "Patliputra", newcomer);
  const acct = await login("accountant.patna@pqr.eraj.test");
  const charges = await getJson(acct.page, `fees/charges?student=${mine.student}&page_size=50`);
  const tcharges = charges.results.filter((c) => /Transport/.test(c.description));
  check("the stop's fare appears on the student's Fees account", tcharges.length >= 1 && Number(tcharges[0].amount) === Number(mine.monthly_fare),
    `${tcharges.length} months × ₹${mine.monthly_fare}`);

  // stop from next month via the list action
  await p.goto(`${BASE}/transport/assignments`);
  await p.locator(".ant-input-search input, input[placeholder*='Search']").first().fill(newcomer);
  await p.keyboard.press("Enter");
  await p.waitForTimeout(1500);
  await rowAction(p, newcomer, "Stop from next month");
  await confirm(p);
  await p.waitForTimeout(1500);
  const left = (await getJson(acct.page, `fees/charges?student=${mine.student}&page_size=50`)).results
    .filter((c) => /Transport/.test(c.description) && !c.cancelled_at);
  check("stopping from next month leaves only this month's transport fee", left.length === 1, `${left.length}`);
  await p.screenshot({ path: `${OUT}/m5-02-riders.png`, fullPage: true });

  // capacity: shrink the van to one free seat, fill it, then one more is refused
  const van = (await getJson(p, "transport/vehicles")).results.find((v) => v.registration_no.startsWith("BR01VN"));
  const r2stop = (await getJson(p, `transport/stops?route=${van.route}`)).results[0];
  await patchJson(p, `transport/vehicles/${van.id}`, { capacity: van.riders + 1 });
  const students = (await getJson(p, "people/students?page_size=100")).results;
  const onBus = new Set((await getJson(p, "transport/assignments?page_size=100")).results.map((a) => a.student));
  const freeKids = students.filter((x) => !onBus.has(x.id));
  const today = new Date().toLocaleDateString("en-CA");
  const ok1 = await postJson(p, "transport/assignments", { student: freeKids[0].id, stop: r2stop.id, vehicle: van.id, start_date: today });
  const ridingStaff = new Set((await getJson(p, "transport/assignments?page_size=100")).results.map((a) => a.staff));
  const freeStaff = (await getJson(p, "people/staff?page_size=100")).results.find((x) => !ridingStaff.has(x.id));
  const no2 = await postJson(p, "transport/assignments", { staff: freeStaff.id, stop: r2stop.id, vehicle: van.id, start_date: today });
  check("a full vehicle refuses one more rider", ok1.status === 201 && no2.status === 409 && /full/.test(no2.body?.detail ?? ""), no2.body?.detail);

  await p.goto(`${BASE}/transport/reports`);
  await p.waitForSelector(".ant-table-row", { timeout: 20000 });
  const pdf = await head(p, "/api/proxy/transport/reports/riders?pdf=1");
  check("stop-wise rider list prints", pdf.head.startsWith("%PDF"));
  await p.getByRole("tab", { name: "Papers expiring" }).click();
  await p.waitForSelector(".ant-tabs-tabpane-active .ant-table-row", { timeout: 20000 });
  const exp = await p.locator(".ant-tabs-tabpane-active .ant-table-row").filter({ hasText: "Insurance" }).count();
  check("insurance due in 20 days is on the expiring list", exp >= 1);
  await p.screenshot({ path: `${OUT}/m5-03-expiring.png`, fullPage: true });

  // ================= store keeper
  const st = await login("store.patna@pqr.eraj.test");
  const s = st.page;
  await s.goto(`${BASE}/inventory/purchases/create`);
  await pickId(s, "vendor", "Patna");
  await s.locator("#bill_no").fill("PS-9001");
  await s.locator("#bill_date").click();
  await s.locator("#bill_date").fill(new Date().toLocaleDateString("en-GB").replace(/\//g, "-"));
  await s.keyboard.press("Enter");
  await s.getByRole("button", { name: "Add item" }).click();
  await pickId(s, "lines_0_item", "Laptop");
  await s.locator("#lines_0_quantity").fill("2");
  await s.locator("#lines_0_rate").fill("36000");
  await s.getByRole("button", { name: "Save" }).click();
  await s.waitForURL(/\/inventory\/purchases$/, { timeout: 20000 });
  const laptop = (await getJson(s, "inventory/items?search=Laptop")).results[0];
  check("store keeper records a direct purchase; stock and value rise", Number(laptop.quantity) === 4, `${laptop.quantity} @ ₹${Number(laptop.avg_cost)}`);

  await s.goto(`${BASE}/inventory/stock?item=${laptop.id}`);
  await s.waitForSelector("text=Item ledger", { timeout: 20000 });
  await pick(s, "Staff member", "Sunita");
  await s.getByLabel("Quantity").first().fill("1");
  await s.getByRole("button", { name: "Issue", exact: true }).click();
  await s.waitForTimeout(1500);
  const held = await getJson(s, "inventory/reports/with-staff");
  check("a returnable laptop is issued to a teacher", held.some((h) => h.item === "Laptop" && /Sunita/.test(h.staff)));
  check("store keeper can't adjust stock (Admin only)", (await s.getByText("Adjust after physical count").count()) === 0);
  await s.screenshot({ path: `${OUT}/m5-04-stock.png`, fullPage: true });

  await s.goto(`${BASE}/inventory/issues`);
  await rowAction(s, "Laptop", "Returned damaged");
  await s.locator(".ant-modal:visible textarea, .ant-modal:visible input").first().fill("Screen cracked");
  await s.locator(".ant-modal:visible .ant-btn-primary").click();
  await s.waitForTimeout(1500);
  const ledger = await getJson(s, `inventory/items/${laptop.id}/ledger`);
  check("returned damaged: ledger shows the issue and the damage note", ledger.some((m) => m.kind === "issue") &&
    ledger.some((m) => m.kind === "damaged" && m.note === "Screen cracked"));

  // ================= approvals → order → partial receipt
  const req = (await getJson(s, "inventory/requisitions?status=pending")).results[0];
  check("the ₹60,000 requisition needs two approvals", req && req.approvals_needed === 2 && Number(req.total) === 60000);
  await acct.page.goto(`${BASE}/inventory/requisitions`);
  await rowAction(acct.page, "Biology", "Approve");
  await acct.page.waitForTimeout(1500);
  const admin = await login("owner@pqr.eraj.test");
  await admin.page.goto(`${BASE}/inventory/requisitions`);
  await rowAction(admin.page, "Biology", "Approve");
  await admin.page.waitForTimeout(1500);
  const approved = await getJson(s, `inventory/requisitions/${req.id}`);
  check("accountant + Admin approve it", approved.status === "approved", approved.approved_by);

  await s.goto(`${BASE}/inventory/orders/create?requisition=${req.id}`);
  await pickId(s, "vendor", "Bihar");
  await s.getByRole("button", { name: "Save" }).click();
  await s.waitForURL(/\/inventory\/orders$/, { timeout: 20000 });
  const order = (await getJson(s, "inventory/orders?status=open")).results.find((o) => o.requisition === req.id);
  check("an order is raised from the approved requisition", Boolean(order), order?.number);
  await s.goto(`${BASE}/inventory/receive?order=${order.id}`);
  await s.getByLabel("receive-Student microscope").fill("6");
  await s.getByRole("button", { name: "Record receipt" }).click();
  await s.waitForURL(/\/inventory\/orders$/, { timeout: 20000 });
  const after60 = await getJson(s, `inventory/orders/${order.id}`);
  check("60% received → partly received", after60.status === "partly" && after60.received_percent === 60);
  const poPdf = await head(s, `/api/proxy/inventory/orders/${order.id}/pdf`);
  check("purchase order prints as PDF", poPdf.head.startsWith("%PDF"));
  await s.screenshot({ path: `${OUT}/m5-05-orders.png`, fullPage: true });

  // ================= Admin adjusts; reports
  await admin.page.goto(`${BASE}/inventory/stock?item=${laptop.id}`);
  await admin.page.waitForSelector("text=Adjust after physical count", { timeout: 20000 });
  await admin.page.getByLabel("Counted quantity").fill("2");
  await admin.page.getByLabel("Reason").fill("Annual count");
  await admin.page.getByRole("button", { name: "Adjust stock" }).click();
  await admin.page.waitForTimeout(1500);
  const lap2 = await getJson(admin.page, `inventory/items/${laptop.id}`);
  check("Admin adjusts stock after a count", Number(lap2.quantity) === 2, lap2.quantity);

  await s.goto(`${BASE}/inventory/reports`);
  await s.waitForSelector(".ant-table-row", { timeout: 20000 });
  await s.getByRole("tab", { name: /Low stock/ }).click();
  await s.waitForTimeout(800);
  const lowRows = await s.locator(".ant-tabs-tabpane-active .ant-table-row").count();
  check("low-stock list shows items at their reorder level", lowRows >= 1, `${lowRows}`);
  await s.screenshot({ path: `${OUT}/m5-06-reports.png`, fullPage: true });

  // ================= mess cost per head (warden)
  const w = await login("warden.patna@pqr.eraj.test");
  const mess = (await getJson(w.page, "hostel/messes")).results[0];
  const cost = await getJson(w.page, `hostel/messes/${mess.id}/cost-per-head`);
  check("mess cost per head uses provisions from the mess store", Number(cost.provisions_value) > 0, `₹${cost.provisions_per_head_day}/head/day`);

  const allErrors = contexts.flatMap((c) => c.errors).filter((e) => !/favicon|DevTools|status of (403|404|409)|tile\.openstreetmap|ERR_|net::/.test(e));
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

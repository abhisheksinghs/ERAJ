// M6 Alerts + Portal + Learning browser walkthrough. Needs: Django on :8000 started with PORTAL_OTP_ECHO=1, a Celery
// worker, `next start` on :3000 and fresh `seed_demo_tenants` data (Class 6-A homework with a PDF, an open 5-question
// quiz, a sent notice; mother 9876500001 with PATNA-C6-002 (day scholar) + PATNA-C7-002 (hostel); student login
// student.patna@pqr.eraj.test).
// Run: OUT=/tmp/shots NODE_PATH=$(npm root -g) node e2e/smoke-m6.mjs
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");

const BASE = "http://pqr.localhost:3000";
const PW = "eraj-demo-pass-123";
const MOTHER = "9876500001";
const OUT = process.env.OUT ?? ".";
const results = [];
const check = (name, ok, extra = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
};
const browser = await chromium.launch();
const contexts = [];
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };
const JPG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46, 0x49, 0x46, 0]), Buffer.alloc(200)]);
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF");
const today = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10); // IST date
const addDays = (d, n) => new Date(new Date(d + "T12:00:00Z").getTime() + n * 86400e3).toISOString().slice(0, 10);

function track(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text()));
  contexts.push({ page, errors });
  return errors;
}
async function staff(email) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  track(page);
  await page.goto(`${BASE}/login`);
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PW);
  await Promise.all([page.waitForURL(/\/dashboard/), page.click('button[type="submit"]')]);
  await page.waitForSelector("text=Welcome", { timeout: 20000 });
  return page;
}
async function parent(phone) {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  track(page);
  await page.goto(`${BASE}/portal/login`);
  await page.fill('input[name="phone"]', phone);
  await Promise.all([page.waitForURL(/step=code/), page.click('button[type="submit"]')]);
  const code = (await page.locator('[data-testid="demo-code"] b').textContent())?.trim();
  await page.fill('input[name="code"]', code ?? "");
  await Promise.all([page.waitForURL(/\/portal($|\?)/), page.click('button[type="submit"]')]);
  await page.waitForSelector("text=Attendance today", { timeout: 20000 });
  return { page, code };
}
async function student(email) {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  track(page);
  await page.goto(`${BASE}/login`);
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PW);
  await Promise.all([page.waitForURL(/\/portal/, { timeout: 30000 }), page.click('button[type="submit"]')]);
  await page.waitForSelector("text=Attendance today", { timeout: 20000 });
  return page;
}
const getJson = (page, path) => page.evaluate(async (p) => (await fetch(`/api/proxy/${p}`)).json(), path);
const send = (page, method, path, body) => page.evaluate(async ([m, p, b]) => {
  const r = await fetch(`/api/proxy/${p}`, { method: m, headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
  return { status: r.status, body: await r.json().catch(() => null) };
}, [method, path, body]);
const postJson = (page, path, body) => send(page, "POST", path, body);
const status = (page, url) => page.evaluate(async (u) => (await fetch(u)).status, url);
const head = (page, url) => page.evaluate(async (u) => {
  const r = await fetch(u);
  return { status: r.status, type: r.headers.get("content-type"), head: new TextDecoder().decode(new Uint8Array(await r.arrayBuffer()).slice(0, 5)) };
}, url);
async function tab(page, name) {
  const bottom = page.locator("nav.portal-bottom button", { hasText: name });
  if (await bottom.count()) await bottom.first().click();
  else {
    await page.locator("nav.portal-bottom button", { hasText: "More" }).click();
    await page.locator(".portal-more button", { hasText: name }).click();
  }
  await page.waitForSelector(`h4:has-text("${name}")`, { timeout: 15000 });
}
async function pickDate(page, scope, field, d) {
  await scope.locator(`#${field}`).click();
  const cell = page.locator(`.ant-picker-dropdown:not(.ant-picker-dropdown-hidden) td.ant-picker-cell-in-view[title="${d}"]`).last();
  await cell.waitFor({ timeout: 10000 });
  await page.waitForTimeout(300); // let the dropdown finish opening
  await cell.click();
  await page.waitForTimeout(400); // and closing, before the next picker
}
const shot = (page, name) => page.screenshot({ path: `${OUT}/m6-${name}.png`, fullPage: true });

try {
  const admin = await staff("owner@pqr.eraj.test");
  const teacher = await staff("teacher.patna@pqr.eraj.test");
  const find = async (adm) => (await getJson(admin, `people/students/?search=${adm}`)).results.find((s) => s.admission_no === adm);
  const c6 = await find("PATNA-C6-002");
  const c7 = await find("PATNA-C7-002");
  const other = await find("PATNA-C6-001");
  const patna = c6.branch;
  const section6 = (await getJson(teacher, "people/sections/?page_size=50")).results.find((s) => String(s.label ?? s.name).includes("6"));

  // ---- PORTAL-1: OTP login, two children, switch
  const { page: mum, code } = await parent(MOTHER);
  check("PORTAL-1 parent signs in with a one-time code", /^\d{6}$/.test(code ?? ""), code);
  const kids = await mum.locator('[data-testid="child-switch"] .ant-segmented-item').allTextContents();
  check("PORTAL-1 one login shows both children", kids.length === 2, kids.join(", "));
  await mum.locator('[data-testid="child-switch"] .ant-segmented-item').nth(1).click();
  await mum.waitForTimeout(800);
  const header2 = await mum.locator("header.portal-top").textContent();
  await mum.locator('[data-testid="child-switch"] .ant-segmented-item').nth(0).click();
  await mum.waitForTimeout(800);
  const header1 = await mum.locator("header.portal-top").textContent();
  check("PORTAL-1 switching child changes the page", header1 !== header2 && (header1 + header2).includes("C6") && (header1 + header2).includes("C7"));
  await shot(mum, "portal-home");
  const firstIsC6 = header1.includes("C6");
  const pickChild = async (page, wantC6) => {
    const items = page.locator('[data-testid="child-switch"] .ant-segmented-item');
    await items.nth(wantC6 === firstIsC6 ? 0 : 1).click();
    await page.waitForTimeout(800);
  };

  // ---- PORTAL-2: teacher marks absent → portal shows it. On a Sunday the latest working day (Saturday) is used:
  // the Admin marks it (a past day) and the parent checks the attendance calendar instead of "today".
  const sunday = new Date(today + "T12:00:00Z").getUTCDay() === 0;
  const onDay = sunday ? addDays(today, -1) : today;
  const marker = sunday ? admin : teacher;
  const mark = await postJson(marker, "attendance/records/mark/", { section: section6.id, date: onDay, absent: [c6.id] });
  check(`PORTAL-2 ${sunday ? "attendance (Saturday, by Admin)" : "teacher"} marks the child absent`, mark.status === 200, JSON.stringify(mark.body).slice(0, 120));
  const t0 = Date.now();
  await mum.reload();
  await mum.waitForSelector("text=Attendance today");
  await pickChild(mum, true);
  let seen;
  if (!sunday) seen = await mum.locator('[data-testid="today-status"]').textContent();
  else {
    await tab(mum, "Attendance");
    await mum.waitForSelector(".portal-cal .d", { timeout: 15000 });
    const dayNo = String(Number(onDay.slice(8)));
    seen = (await mum.locator(".portal-cal .d.absent", { hasText: new RegExp(`^${dayNo}$`) }).count()) ? "Absent" : "missing";
  }
  check("PORTAL-2 parent sees Absent on the portal within 5 minutes", seen?.includes("Absent") && Date.now() - t0 < 300000, `${seen} in ${Math.round((Date.now() - t0) / 1000)}s`);
  await shot(mum, "portal-attendance");
  if (!sunday) {
    const absentMsg = (await getJson(admin, `notify/messages/?student=${c6.id}&event=attendance.absent`)).results ?? [];
    check("Alerts: the absent alert is in the delivery log", absentMsg.length >= 1, absentMsg.map((m) => `${m.channel}:${m.status}`).join(" "));
  }

  // ---- PORTAL-3: receipt + published report card only
  const accountant = await staff("accountant.patna@pqr.eraj.test");
  const rc = await postJson(accountant, "fees/receipts/", { student: c6.id, mode: "cash", amount: "500" });
  check("PORTAL-3 accountant collects a payment", rc.status === 201, String(rc.status));
  const exams = (await getJson(admin, "exam/exams/?page_size=50")).results.filter((e) => String(e.program_name ?? e.program).includes("6") || e.program === c6.program);
  const half = exams.find((e) => e.name === "Half-Yearly");
  const annual = exams.find((e) => e.name === "Annual");
  const pub = await postJson(admin, `exam/exams/${half.id}/publish/`, {});
  await tab(mum, "Fees");
  await mum.waitForSelector("text=Receipts");
  const rlink = await mum.locator('a[aria-label^="receipt"]').first().getAttribute("href");
  const r1 = await head(mum, rlink);
  check("PORTAL-3 fee receipt downloads as a PDF", r1.status === 200 && r1.head === "%PDF-", `${r1.status} ${r1.type}`);
  await shot(mum, "portal-fees");
  await tab(mum, "Results");
  await mum.waitForSelector("text=Half-Yearly");
  const cardHref = await mum.locator("a", { hasText: "Report card" }).first().getAttribute("href");
  const r2 = await head(mum, cardHref);
  const annualStatus = await status(mum, `/api/proxy/portal/children/${c6.id}/report-card/?exam=${annual.id}&_branch=${patna}`);
  const annualListed = await mum.locator("text=Annual").count();
  check("PORTAL-3 published report card downloads; unpublished is not visible", pub.status === 200 && r2.head === "%PDF-" && annualStatus === 404 && annualListed === 0,
    `card ${r2.status}, annual ${annualStatus}`);
  await shot(mum, "portal-results");

  // ---- PORTAL-4: outpass by parent → warden approves → portal shows approved
  await pickChild(mum, false);
  await tab(mum, "Hostel");
  const form = mum.locator("form").filter({ hasText: "Reason" }).first();
  await pickDate(mum, form, "from", addDays(today, 3));
  await pickDate(mum, form, "to", addDays(today, 4));
  await form.locator("#reason").fill("Cousin's wedding");
  await form.locator("#destination").fill("Gaya");
  await form.locator('button[type="submit"]').click();
  await mum.waitForSelector('[data-testid^="outpass-"]', { timeout: 15000 });
  const ops = (await getJson(admin, `hostel/outpasses/?student=${c7.id}`)).results ?? [];
  const op = ops.find((o) => o.reason === "Cousin's wedding");
  const warden = await staff("warden.patna@pqr.eraj.test");
  const ap = await postJson(warden, `hostel/outpasses/${op?.id}/approve/`, { note: "Return by 6 pm" });
  await tab(mum, "Home");
  await tab(mum, "Hostel");
  const opTag = await mum.locator(`[data-testid="outpass-${op?.id}"] .ant-tag`).textContent();
  check("PORTAL-4 parent requests an outpass; warden approves; portal shows Approved", op?.requested_by === "parent" && ap.status === 200 && opTag === "Approved",
    `${opTag}; by ${op?.requested_by}; approve ${ap.status} ${JSON.stringify(ap.body).slice(0, 80)}`);
  await shot(mum, "portal-outpass");

  // ---- PORTAL-5: another child, by URL
  const idor = await status(mum, `/api/proxy/portal/children/${other.id}/?_branch=${patna}`);
  const idorFees = await status(mum, `/api/proxy/portal/children/${other.id}/fees/?_branch=${patna}`);
  await mum.goto(`${BASE}/portal?child=${other.id}`);
  await mum.waitForSelector("text=Attendance today");
  const shown = await mum.locator("header.portal-top").textContent();
  check("PORTAL-5 another student's records are refused, also by editing the address", idor === 404 && idorFees === 404 && !shown.includes(other.full_name),
    `${idor}/${idorFees}`);

  // ---- LRN-1: homework with a PDF; student submits a photo; teacher grades; parent sees the grade
  const hws = (await getJson(teacher, `learning/homework/?section=${section6.id}`)).results;
  const hw = hws.find((h) => h.title.startsWith("Fractions"));
  const late = hws.find((h) => h.title.startsWith("Decimals"));
  await teacher.goto(`${BASE}/learning/review?homework=${hw.id}`);
  await teacher.waitForSelector("text=Attachments");
  await teacher.locator('[data-testid="attach"]').setInputFiles({ name: "answers-key.pdf", mimeType: "application/pdf", buffer: PDF });
  await teacher.waitForSelector("text=answers-key.pdf", { timeout: 15000 });
  check("LRN-1 teacher attaches a PDF to the homework", (await teacher.locator("a", { hasText: ".pdf" }).count()) >= 2);
  const kid = await student("student.patna@pqr.eraj.test");
  await tab(kid, "Homework");
  await kid.locator(`[data-testid="files-${hw.id}"]`).setInputFiles({ name: "page1.jpg", mimeType: "image/jpeg", buffer: JPG });
  await kid.locator(`[data-testid="hw-${hw.id}"] button`, { hasText: "Submit work" }).click();
  await kid.waitForSelector(`[data-testid="hw-${hw.id}"] .ant-tag:has-text("Submitted")`, { timeout: 15000 });
  check("LRN-1 student submits a photo from the portal", true);
  await shot(kid, "student-homework");
  await teacher.reload();
  await teacher.waitForSelector("text=Submissions (1)", { timeout: 15000 });
  const subId = (await getJson(teacher, `learning/submissions/?homework=${hw.id}`)).results[0].id;
  await teacher.fill(`input[aria-label="grade-${subId}"]`, "A");
  await teacher.fill(`input[aria-label="remarks-${subId}"]`, "Neat work");
  await teacher.locator("tr", { has: teacher.locator(`input[aria-label="grade-${subId}"]`) }).locator("button", { hasText: "Save" }).click();
  await teacher.waitForSelector("text=Checked", { timeout: 15000 });
  await shot(teacher, "teacher-review");
  await pickChild(mum, true);
  await tab(mum, "Homework");
  const g = await mum.locator(`[data-testid="grade-${hw.id}"]`).textContent();
  check("LRN-1 parent sees the grade on the portal", g?.includes("A") && g.includes("Neat work"), g);

  // ---- LRN-2: after the due date → marked late
  await tab(kid, "Home");
  await tab(kid, "Homework");
  await kid.fill(`textarea[aria-label="answer-${late.id}"]`, "Done — page 12");
  await kid.locator(`[data-testid="hw-${late.id}"] button`, { hasText: "Submit work" }).click();
  await kid.waitForSelector(`[data-testid="hw-${late.id}"] .ant-tag:has-text("Late")`, { timeout: 15000 });
  await teacher.goto(`${BASE}/learning/review?homework=${late.id}`);
  await teacher.waitForSelector("text=Submissions (1)");
  check("LRN-2 a submission after the due date is marked late", (await teacher.locator(".ant-tag", { hasText: "Late" }).count()) === 1);

  // ---- LRN-3: online class in timetable + portal; join record
  const maths = (await getJson(teacher, "people/subjects/?search=Mathematics&page_size=50")).results.find((s) => s.code === "C6-MAT");
  const startsAt = new Date(Date.now() + 5 * 60e3).toISOString();
  const endsAt = new Date(Date.now() + 50 * 60e3).toISOString();
  const cls = await postJson(teacher, "learning/classes/", { section: section6.id, subject: maths.id, title: "Live revision", starts_at: startsAt, ends_at: endsAt,
    link: "https://meet.google.com/xyz-abcd-efg" });
  const grid = await getJson(teacher, `timetable/views/section/?section=${section6.id}&date=${today}`);
  await tab(kid, "Timetable");
  const inTimetable = await kid.locator("text=Live revision").first().waitFor({ timeout: 15000 }).then(() => 1).catch(() => 0);
  await tab(kid, "Online classes & tests");
  const card = kid.locator(".ant-card", { hasText: "Live revision" });
  const [popup] = await Promise.all([kid.context().waitForEvent("page", { timeout: 15000 }).catch(() => null), card.locator("button", { hasText: "Join class" }).click()]);
  await popup?.close().catch(() => undefined);
  await teacher.goto(`${BASE}/learning/review?class=${cls.body.id}`);
  await teacher.waitForSelector("text=Opened the class link");
  const joinedTxt = await teacher.locator("text=Opened the class link").textContent();
  check("LRN-3 class appears in the timetable and portal; join record lists the student",
    cls.status === 201 && grid.online.some((o) => o.id === cls.body.id) && inTimetable >= 1 && /1\s*\/\s*\d/.test(joinedTxt ?? ""),
    `${joinedTxt}; staff timetable ${grid.online.length} online; portal ${inTimetable}`);
  await shot(teacher, "class-joins");

  // ---- LRN-4: 10-question test scored automatically
  const questions = Array.from({ length: 10 }, (_, i) => ({ sequence: i + 1, text: `${i + 2} × 3 = ?`, options: [String((i + 2) * 3), String((i + 2) * 3 + 1)], correct: 0, marks: 1 }));
  const test = await postJson(teacher, "learning/tests/", { section: section6.id, subject: maths.id, title: "Tables test", opens_at: new Date(Date.now() - 5 * 60e3).toISOString(),
    closes_at: new Date(Date.now() + 2 * 3600e3).toISOString(), time_limit_minutes: 10, published: true, show_answers: true, questions });
  await teacher.goto(`${BASE}/learning/test?id=${test.body.id}`);
  await teacher.waitForSelector("text=Questions (10)");
  await tab(kid, "Home");
  await tab(kid, "Online classes & tests");
  await kid.locator(".ant-card", { hasText: "Tables test" }).locator("button", { hasText: "Start test" }).click();
  await kid.waitForSelector(".ant-modal-content");
  for (let n = 1; n <= 10; n++) {
    const input = kid.locator(`.ant-modal-content input[aria-label="q${n}-${n <= 7 ? 0 : 1}"]`);
    await kid.locator(".ant-modal-content label.ant-radio-wrapper", { has: kid.locator(`input[aria-label="q${n}-${n <= 7 ? 0 : 1}"]`) }).click();
    await kid.waitForFunction((el) => el?.checked, await input.elementHandle());
  }
  await shot(kid, "student-test");
  await kid.locator(".ant-modal-footer button", { hasText: "Submit answers" }).click();
  const score = await kid.locator('[data-testid="test-score"]').textContent({ timeout: 15000 });
  await teacher.reload();
  await teacher.locator(".ant-tabs-tab", { hasText: "Scores" }).click();
  const teacherSees = await teacher.locator("td", { hasText: /^7(\.00)? \/ 10(\.00)?/ }).first().waitFor({ timeout: 15000 }).then(() => 1).catch(() => 0);
  const pane = (await teacher.locator(".ant-tabs-tabpane-active").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 160);
  check("LRN-4 10-question test: score calculated automatically", /7(\.00)? \/ 10/.test(score ?? "") && teacherSees === 1, `${score}; teacher sees: ${pane}`);

  // ---- notices with read status, day-scholar leave, change request
  const notices = (await getJson(admin, "notify/notices/")).results;
  const ptm = notices.find((n) => n.title === "Parent-teacher meeting" && n.branch === patna);
  await tab(mum, "Notices");
  await mum.locator(".ant-list-item", { hasText: "Parent-teacher meeting" }).click();
  await mum.waitForTimeout(1200);
  await admin.goto(`${BASE}/notify/reads?notice=${ptm.id}`);
  await admin.waitForSelector("text=Who has read the notice");
  const readTxt = await admin.locator("text=Read:").first().textContent();
  check("Notices: parent opens the notice; the office sees it as read", /Read:\s*1\b/.test(readTxt ?? ""), readTxt);

  await tab(mum, "Leave & changes");
  const leaveForm = mum.locator("form").filter({ hasText: "First day of leave" }).first();
  await pickDate(mum, leaveForm, "from", addDays(today, 1));
  await leaveForm.locator("#reason").fill("Family function");
  await leaveForm.locator('button[type="submit"]').click();
  await mum.waitForSelector(".ant-tag:has-text('Waiting')", { timeout: 15000 });
  await teacher.goto(`${BASE}/portal/leaves`);
  await teacher.waitForSelector("text=Family function", { timeout: 20000 });
  const lv = (await getJson(teacher, "portal/leaves/?status=requested")).results.find((x) => x.reason === "Family function");
  const dec = await postJson(teacher, `portal/leaves/${lv.id}/decide/`, { approve: true });
  check("Leave: day-scholar leave reaches the class teacher and is approved", dec.status === 200 && dec.body.status === "approved");

  const changeForm = mum.locator("form").filter({ hasText: "New value" }).first();
  await changeForm.locator("#new_value").fill("House 12, Boring Road, Patna");
  await changeForm.locator('button[type="submit"]').click();
  await mum.waitForSelector("text=House 12, Boring Road", { timeout: 15000 });
  await admin.goto(`${BASE}/portal/change-requests`);
  await admin.waitForSelector("text=House 12, Boring Road", { timeout: 20000 });
  const cr = (await getJson(admin, `portal/change-requests/?status=requested`)).results.find((x) => x.new_value.startsWith("House 12"));
  const before = (await getJson(admin, `people/students/${c6.id}/`)).address;
  const okc = await postJson(admin, `portal/change-requests/${cr.id}/decide/`, { approve: true });
  const after = (await getJson(admin, `people/students/${c6.id}/`)).address;
  check("Change request applies only after the office approves", before !== "House 12, Boring Road, Patna" && okc.status === 200 && after === "House 12, Boring Road, Patna");
  await shot(mum, "portal-requests");

  // ---- staff screens render
  for (const path of ["learning/homework", "learning/materials", "learning/classes", "learning/tests", "learning/diary", "learning/upload", "learning/reports",
    "notify/notices", "notify/messages", "notify/rules", "notify/templates", "notify/channels", "notify/settings", "notify/opt-outs", "notify/usage",
    "portal/leaves", "portal/change-requests", "portal/student-logins"]) {
    await admin.goto(`${BASE}/${path}`);
    await admin.waitForSelector("h3, .ant-table, .ant-card", { timeout: 20000 });
  }
  await admin.goto(`${BASE}/notify/messages`);
  await admin.waitForSelector(".ant-table-row", { timeout: 20000 });
  const otpRows = await getJson(admin, "notify/messages/?event=portal.otp");
  check("Alerts: login codes are never readable in the delivery log", (otpRows.results ?? []).every((m) => !/\d{6}/.test(m.body)), `${otpRows.count} code messages`);
  await shot(admin, "delivery-log");
  check("Staff screens for Learning, Alerts and Portal open", true);
} catch (e) {
  check("walkthrough ran to the end", false, String(e).slice(0, 400));
  for (const [i, c] of contexts.entries()) await c.page.screenshot({ path: `${OUT}/m6-fail-${i}.png`, fullPage: true }).catch(() => undefined);
} finally {
  const errs = contexts.flatMap((c) => c.errors);
  check("no browser errors", errs.length === 0, errs.slice(0, 3).join(" | "));
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}

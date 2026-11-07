// Production smoke test: creates TEST data, runs the full teacher flow on a phone screen, then deletes it.
// Run: PASS=... node e2e/production_smoke.cjs  (needs a temporary admin account)
const { chromium, devices } = require("playwright");
const assert = require("assert");
const BASE = process.env.BASE_URL || "https://school-attendance-burk.onrender.com";
const USER = process.env.USER_NAME || "claude_test", PASS = process.env.PASS;  // never commit the password
const SHOTS = process.env.SHOTS || ".";
const MARK = "[TEST] ทดสอบระบบโดย Claude";

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices["Pixel 7"] });
  const page = await ctx.newPage();
  page.on("dialog", (d) => d.accept());
  const problems = [];
  page.on("console", (m) => { if (m.type() === "error" && !/status of 401/.test(m.text())) problems.push(m.text()); });
  page.on("pageerror", (e) => problems.push(e.message));
  const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true });
  const step = (s) => console.log("ok  " + s);
  let csrf = "";
  const api = (method, url, data) => page.evaluate(async ([method, url, data, csrf]) => {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: data ? JSON.stringify(data) : undefined });
    return { status: r.status, body: r.status === 204 ? null : await r.json().catch(() => null) };
  }, [method, url, data, csrf]);

  // Login: wrong password, then right one
  await page.goto(BASE + "/");
  assert.match(page.url(), /\/login/);
  await page.fill("#username", USER); await page.fill("#password", "wrong-pass-1");
  await page.click("button[type=submit]");
  await page.waitForSelector("#login-error:not(.hidden)");
  await page.fill("#password", PASS); await page.click("button[type=submit]");
  await page.waitForURL(BASE + "/");
  csrf = await page.getAttribute('meta[name="csrf-token"]', "content");
  step("login (wrong password rejected, right password accepted)");

  // Setup via API: test term (today only window), subject, period
  const today = (await api("GET", "/api/attendance/options")).body.today;
  const term = await api("POST", "/api/admin/terms", { academic_year: 2569, term_no: 3, start_date: "2026-11-01", end_date: today, is_current: true });
  assert.strictEqual(term.status, 201, JSON.stringify(term.body));
  const subj = await api("POST", "/api/admin/subjects", { subject_code: "TEST", name: "วิชาทดสอบ (ลบได้)" });
  assert.strictEqual(subj.status, 201, JSON.stringify(subj.body));
  const per = await api("POST", "/api/admin/periods", { period_no: 20, start_time: "00:00", end_time: "23:59" });
  assert.strictEqual(per.status, 201, JSON.stringify(per.body));
  console.log(JSON.stringify({ term: term.body.id, subject: subj.body.id, period: per.body.id }));
  step("create test term / subject / period");

  // Import students through the UI
  await page.goto(BASE + "/admin/students");
  await page.setInputFiles("#imp-file", process.env.XLSX || "e2e/test_students.xlsx");
  await page.fill("#imp-year", "2569");
  await page.click("#imp-preview");
  await page.waitForSelector("#imp-commit:not(.hidden)");
  await shot("01-import-preview");
  await page.click("#imp-commit");
  await page.waitForSelector("#toast.success");
  await page.waitForFunction(() => document.querySelectorAll("#s-body tr").length >= 3);
  step("import 3 students from .xlsx (preview + commit)");

  // Take attendance on the phone
  await page.goto(BASE + "/");
  await page.waitForFunction(() => [...document.querySelectorAll("#f-room option")].some(o => o.textContent === "ทดสอบ/1"));
  await page.selectOption("#f-room", { label: "ทดสอบ/1" });
  await page.selectOption("#f-period", { value: String(per.body.id) });
  await page.selectOption("#f-area", { label: "อื่นๆ" });
  await page.selectOption("#f-subject", { value: String(subj.body.id) });
  await page.waitForSelector("#students li");
  assert.strictEqual(await page.locator("#students li").count(), 3);
  await page.locator("#students li").nth(1).getByRole("button", { name: "ขาด" }).click();
  await page.locator("#students li").nth(2).getByRole("button", { name: "ลา", exact: true }).click();
  await page.locator("#students li").nth(1).locator("input.note").fill("ทดสอบหมายเหตุ");
  await page.fill("#f-topic", MARK);
  await shot("02-attendance");
  await page.click("#save-btn");
  await page.waitForSelector("#toast.success");
  step("save attendance (1 present, 1 absent, 1 leave)");

  await page.reload();
  await page.selectOption("#f-room", { label: "ทดสอบ/1" });
  await page.selectOption("#f-period", { value: String(per.body.id) });
  await page.waitForSelector("#saved-info:not(.hidden)");
  assert.strictEqual(await page.inputValue("#f-topic"), MARK);
  assert.strictEqual(await page.locator("#students li").nth(1).getByRole("button", { name: "ขาด" }).getAttribute("aria-pressed"), "true");
  step("reload shows the saved check");

  await page.goto(BASE + "/history");
  await page.waitForSelector("#h-body tr");
  assert.match(await page.textContent("#h-body"), /ทดสอบ\/1/);
  step("history");
  await page.goto(BASE + "/dashboard");
  await page.waitForSelector("#d-content:not(.hidden)");
  await shot("03-dashboard");
  assert.match(await page.textContent("#d-content"), /ทดสอบสอง/);
  step("daily dashboard lists the absent student");

  await page.goto(BASE + "/reports");
  await page.waitForFunction(() => document.querySelector("#r-room").options.length > 1);
  await page.selectOption("#r-room", { label: "ทดสอบ/1" });
  await page.selectOption("#r-subject", { value: String(subj.body.id) });
  await page.click("#r-show");
  await page.waitForSelector("#r-result:not(.hidden)");
  const href = await page.getAttribute("#r-print", "href");
  await page.goto(BASE + href);
  assert.match(await page.textContent("body"), /แบบบันทึกเวลาเรียน/);
  assert.match(await page.textContent("body"), /ทดสอบระบบโดย Claude/);
  await page.emulateMedia({ media: "print" });
  await page.pdf({ path: `${SHOTS}/04-term-report.pdf`, format: "A4", landscape: true, printBackground: true }).catch(() => {});
  await page.emulateMedia({ media: "screen" });
  await shot("04-report-print");
  step("term report + print page");

  for (const p of ["/account", "/admin/settings"]) { await page.goto(BASE + p); await page.waitForLoadState("networkidle"); }
  step("account + settings pages load");

  // Cleanup: everything created above
  const sessions = (await api("GET", "/api/attendance/sessions")).body;
  for (const s of sessions.filter(s => (s.topic || "") === MARK)) assert.strictEqual((await api("DELETE", `/api/attendance/sessions/${s.id}`)).status, 204);
  const studs = (await api("GET", "/api/admin/students?q=TEST00")).body;
  for (const s of studs) assert.strictEqual((await api("DELETE", `/api/admin/students/${s.id}`)).status, 204);
  const rooms = (await api("GET", "/api/admin/classrooms?academic_year=2569")).body.filter(r => r.grade_level === "ทดสอบ");
  for (const r of rooms) assert.strictEqual((await api("DELETE", `/api/admin/classrooms/${r.id}`)).status, 204);
  assert.strictEqual((await api("DELETE", `/api/admin/subjects/${subj.body.id}`)).status, 204);
  assert.strictEqual((await api("DELETE", `/api/admin/periods/${per.body.id}`)).status, 204);
  assert.strictEqual((await api("DELETE", `/api/admin/terms/${term.body.id}`)).status, 204);
  const left = {};
  for (const p of ["terms", "subjects", "periods", "students"]) left[p] = (await api("GET", "/api/admin/" + p)).body.length;
  left.sessions = (await api("GET", "/api/attendance/sessions")).body.length;
  console.log("left after cleanup", JSON.stringify(left));
  step("cleanup");

  await browser.close();
  if (problems.length) { console.error("Browser console errors:\n" + problems.join("\n")); process.exit(1); }
  console.log("ALL PRODUCTION CHECKS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });

// End-to-end check of the main teacher flow on a phone-sized screen.
// Needs a running server with demo data (python -m scripts.seed_demo).
// Run:  BASE_URL=http://localhost:8000 node e2e/mobile_flow.cjs
const { chromium, devices } = require("playwright");
const assert = require("assert");

const BASE = process.env.BASE_URL || "http://localhost:8000";
const SHOTS = process.env.SHOTS_DIR || "";

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices["Pixel 7"] });
  const page = await ctx.newPage();
  const problems = [];
  // The deliberate wrong-password login logs a 401; anything else is a real problem.
  page.on("console", (m) => { if (m.type() === "error" && !/status of 401/.test(m.text())) problems.push(m.text()); });
  page.on("pageerror", (e) => problems.push(e.message));
  const shot = async (name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

  // 1. Login (wrong password first)
  await page.goto(BASE + "/");
  assert.match(page.url(), /\/login/);
  await page.fill("#username", "teacher1");
  await page.fill("#password", "wrong-password");
  await page.click("button[type=submit]");
  await page.waitForSelector("#login-error:not(.hidden)");
  assert.match(await page.textContent("#login-error"), /ไม่ถูกต้อง/);
  await page.fill("#password", "demo12345");
  await page.click("button[type=submit]");
  await page.waitForURL(BASE + "/");
  console.log("ok  login");

  // 2. Choose room + period + subject, mark two students
  await page.selectOption("#f-room", { label: "ม.1/1" });
  await page.selectOption("#f-period", { index: 1 });
  await page.selectOption("#f-area", { label: "คณิตศาสตร์" });
  await page.selectOption("#f-subject", { index: 1 });
  await page.waitForSelector("#students li");
  assert.strictEqual(await page.locator("#students li").count(), 30);
  await page.locator("#students li").nth(1).getByRole("button", { name: "ขาด" }).click();
  await page.locator("#students li").nth(4).getByRole("button", { name: "ลา", exact: true }).click();
  await page.locator("#students li").nth(1).locator("input.note").fill("ไม่สบาย โทรแจ้ง");
  assert.match(await page.textContent("#summary"), /มา 28/);
  await page.fill("#f-topic", "สมการเชิงเส้นตัวแปรเดียว");
  await shot("01-attendance-mobile");
  await page.click("#save-btn");
  await page.waitForSelector("#toast.success");
  assert.match(await page.textContent("#toast"), /มา 28/);
  await page.waitForSelector("#saved-info:not(.hidden)");
  console.log("ok  save attendance");

  // 3. Reload: the saved check comes back
  await page.reload();
  await page.selectOption("#f-room", { label: "ม.1/1" });
  await page.selectOption("#f-period", { index: 1 });
  await page.waitForSelector("#saved-info:not(.hidden)");
  assert.strictEqual(await page.inputValue("#f-topic"), "สมการเชิงเส้นตัวแปรเดียว");
  assert.strictEqual(await page.locator("#students li").nth(1).getByRole("button", { name: "ขาด" }).getAttribute("aria-pressed"), "true");
  console.log("ok  reload shows saved check");

  // 4. History, dashboard, report
  await page.goto(BASE + "/history");
  await page.waitForSelector("#h-body tr");
  console.log("ok  history");
  await page.goto(BASE + "/dashboard");
  await page.waitForSelector("#d-content:not(.hidden)");
  assert.match(await page.textContent("#d-stats"), /28/);
  await shot("02-dashboard-mobile");
  console.log("ok  dashboard");
  await page.goto(BASE + "/reports");
  await page.waitForFunction(() => document.querySelector("#r-room").options.length > 1);
  await page.selectOption("#r-room", { label: "ม.1/1" });
  await page.selectOption("#r-subject", { index: 1 });
  await page.click("#r-show");
  await page.waitForSelector("#r-result:not(.hidden)");
  const href = await page.getAttribute("#r-print", "href");
  await page.goto(BASE + href);
  assert.match(await page.textContent("body"), /แบบบันทึกเวลาเรียน/);
  assert.match(await page.textContent("body"), /สมการเชิงเส้นตัวแปรเดียว/);
  await shot("03-report-print");
  console.log("ok  term report + print page");

  // 5. Teacher cannot open admin pages
  await page.goto(BASE + "/admin/settings");
  assert.strictEqual(page.url(), BASE + "/");
  console.log("ok  admin pages blocked for teacher");

  // 6. Admin pages load without script errors
  await page.click("#menu-btn");
  await page.click("#logout-btn");
  await page.waitForURL(/\/login/);
  await page.fill("#username", "admin");
  await page.fill("#password", "demo12345");
  await page.click("button[type=submit]");
  await page.waitForURL(BASE + "/");
  await page.goto(BASE + "/admin/settings");
  await page.waitForSelector("#t-body tr");
  for (const t of ["terms", "classrooms", "subjects", "periods"]) {
    await page.click(`[data-tab=${t}]`);
    await page.waitForSelector("#t-body tr");
  }
  await page.goto(BASE + "/admin/students");
  await page.waitForSelector("#s-body tr");
  await shot("04-admin-students");
  console.log("ok  admin pages");

  await browser.close();
  if (problems.length) {
    console.error("Browser console errors:\n" + problems.join("\n"));
    process.exit(1);
  }
  console.log("ALL E2E CHECKS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });

// A teacher saves the wrong period, another teacher is blocked, the recorder moves it, then deletes it.
// Needs a running server with demo data plus a second teacher "teacher2" (password demo12345).
// Run:  BASE_URL=http://localhost:8000 node e2e/wrong_period.cjs
const { chromium, devices } = require("playwright");
const assert = require("assert");

const BASE = process.env.BASE_URL || "http://localhost:8000";
const SHOTS = process.env.SHOTS_DIR || "";

async function login(browser, username) {
  const ctx = await browser.newContext({ ...devices["Pixel 7"] });
  const page = await ctx.newPage();
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(e.message));
  page.on("dialog", (d) => d.accept());
  await page.goto(BASE + "/login");
  await page.fill("#username", username);
  await page.fill("#password", "demo12345");
  await page.click("button[type=submit]");
  await page.waitForURL(BASE + "/");
  return page;
}

async function open(page, periodIndex) {
  await page.selectOption("#f-room", { label: "ม.1/2" });
  await page.selectOption("#f-period", { index: periodIndex });
  await page.waitForSelector("#students li");
}

(async () => {
  const browser = await chromium.launch();
  const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };

  // Teacher 1 records period 3 by mistake.
  const a = await login(browser, "teacher1");
  await open(a, 3);
  await a.selectOption("#f-area", { label: "คณิตศาสตร์" });
  await a.selectOption("#f-subject", { index: 1 });
  await a.fill("#f-topic", "ทดสอบผิดคาบ");
  await a.click("#save-btn");
  await a.waitForSelector("#saved-actions:not(.hidden)");
  console.log("ok  teacher1 saved period 3");

  // Teacher 2 is blocked and told what to do.
  const b = await login(browser, "teacher2");
  await open(b, 3);
  await b.waitForSelector("#saved-info:not(.hidden)");
  assert.match(await b.textContent("#saved-text"), /ย้ายไปคาบอื่น/);
  assert.ok(await b.locator("#saved-actions").isHidden());
  assert.ok(await b.locator("#savebar").isHidden());
  await shot(b, "blocked");
  console.log("ok  teacher2 sees read-only with guidance");

  // Teacher 1 moves it to period 2.
  await a.click("#move-btn");
  await a.selectOption("#move-period", { index: 2 });
  await shot(a, "move-dialog");
  await a.click("#move-ok");
  await a.waitForFunction(() => document.querySelector("#saved-edit")?.textContent.includes("แก้ไขล่าสุดโดย"));
  assert.strictEqual(await a.inputValue("#f-topic"), "ทดสอบผิดคาบ");
  assert.strictEqual(await a.$eval("#f-period", (el) => el.selectedIndex), 2);
  await shot(a, "moved");
  console.log("ok  moved to period 2, topic kept, edit shown");

  // Teacher 2 can now record period 3.
  await b.selectOption("#f-period", { index: 1 });
  await b.selectOption("#f-period", { index: 3 });
  await b.waitForFunction(() => document.querySelector("#saved-info").classList.contains("hidden"));
  await b.selectOption("#f-area", { label: "คณิตศาสตร์" });
  await b.selectOption("#f-subject", { index: 1 });
  await b.click("#save-btn");
  await b.waitForSelector("#saved-actions:not(.hidden)");
  console.log("ok  teacher2 recorded period 3");

  // History shows the edit.
  await a.goto(BASE + "/history");
  await a.waitForSelector("#h-body tr");
  assert.match(await a.textContent("#h-body"), /แก้ไขล่าสุดโดย/);
  await shot(a, "history");
  console.log("ok  history shows last edit");

  // Teacher 1 deletes their record (confirm dialog auto-accepted).
  await a.goto(BASE + "/?" + new URLSearchParams({ period: await a.$eval("#h-body a", (el) => new URL(el.href).searchParams.get("period")), room: await a.$eval("#h-body a", (el) => new URL(el.href).searchParams.get("room")) }));
  await a.waitForSelector("#saved-actions:not(.hidden)");
  await a.click("#delete-btn");
  await a.waitForFunction(() => document.querySelector("#saved-info").classList.contains("hidden"));
  console.log("ok  recorder deleted own record");

  const problems = [...a.problems, ...b.problems];
  assert.deepStrictEqual(problems, []);
  await browser.close();
  console.log("ALL WRONG-PERIOD CHECKS PASSED");
})().catch((e) => { console.error(e); process.exit(1); });

// Shared helpers: API calls with CSRF header, toasts, Thai labels and dates, DOM helpers.
"use strict";

const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";

// The school uses three statuses. "ลา" is stored as personal_leave; report APIs call it "leave".
const STATUS = [
  { key: "present", label: "มา" },
  { key: "personal_leave", label: "ลา" },
  { key: "absent", label: "ขาด" },
];
const STATUS_LABEL = { present: "มา", personal_leave: "ลา", leave: "ลา", absent: "ขาด", late: "มา", sick_leave: "ลา" };
// Older records may hold "late" or "sick_leave"; show them as มา / ลา.
const normalStatus = (s) => (s === "late" ? "present" : s === "sick_leave" ? "personal_leave" : s);
const LEARNING_AREAS = [
  "ภาษาไทย", "คณิตศาสตร์", "วิทยาศาสตร์และเทคโนโลยี", "สังคมศึกษา ศาสนาและวัฒนธรรม",
  "สุขศึกษาและพลศึกษา", "ศิลปะ", "การงานอาชีพ", "ภาษาต่างประเทศ", "กิจกรรมพัฒนาผู้เรียน",
];
const THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, headers: { Accept: "application/json" }, credentials: "same-origin" };
  if (method !== "GET") opts.headers["X-CSRF-Token"] = CSRF;
  if (form) {
    opts.body = form; // FormData: browser sets the multipart header itself
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่", 0);
  }
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    window.location.href = "/login?next=" + encodeURIComponent(location.pathname);
    throw new ApiError("กรุณาเข้าสู่ระบบ", 401);
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const msg = data && typeof data.detail === "string" ? data.detail : "เกิดข้อผิดพลาด กรุณาลองใหม่";
    throw new ApiError(msg, res.status);
  }
  return data;
}

let toastTimer;
function toast(message, kind = "") {
  const el = document.getElementById("toast");
  if (!el) return alert(message);
  el.textContent = message;
  el.className = "show " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ""), kind === "error" ? 5000 : 2500);
}

function thaiDate(iso, short = true) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const by = y + 543;
  return `${d} ${THAI_MONTHS[m - 1]} ${short ? String(by).slice(2) : by}`;
}

// "9 พ.ย. 69 19:05" in the device's local time, from an ISO timestamp with a UTC offset.
function thaiDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getDate()} ${THAI_MONTHS[d.getMonth()]} ${String(d.getFullYear() + 543).slice(2)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Build an element: h("td", {class: "num"}, "12"). Text is always set as text, never HTML.
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function fillSelect(select, items, { value = "id", label = "name", placeholder } = {}) {
  const current = select.value;
  select.replaceChildren();
  if (placeholder) select.append(h("option", { value: "" }, placeholder));
  for (const it of items) {
    select.append(h("option", { value: typeof value === "function" ? value(it) : it[value] }, typeof label === "function" ? label(it) : it[label]));
  }
  if ([...select.options].some((o) => o.value === current)) select.value = current;
}

async function withBusy(button, fn) {
  const old = button.textContent;
  button.disabled = true;
  button.textContent = "กำลังดำเนินการ...";
  try { return await fn(); } finally { button.disabled = false; button.textContent = old; }
}

// Navigation menu + logout, present on every signed-in page.
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("menu-btn");
  const nav = document.getElementById("nav");
  const backdrop = document.getElementById("nav-backdrop");
  const setOpen = (open) => {
    nav.classList.toggle("open", open);
    backdrop.hidden = !open;
    document.body.classList.toggle("no-scroll", open);
    btn.setAttribute("aria-expanded", String(open));
    if (open) nav.querySelector("a, button").focus();
  };
  if (btn && nav && backdrop) {
    btn.addEventListener("click", () => setOpen(!nav.classList.contains("open")));
    backdrop.addEventListener("click", () => setOpen(false));
    document.getElementById("menu-close").addEventListener("click", () => { setOpen(false); btn.focus(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && nav.classList.contains("open")) { setOpen(false); btn.focus(); } });
  }
  const logout = document.getElementById("logout-btn");
  if (logout) logout.addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* go to login anyway */ }
    window.location.href = "/login";
  });
});

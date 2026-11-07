// Shared helpers: API calls with CSRF header, toasts, Thai labels and dates, DOM helpers.
"use strict";

const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";

const STATUS = [
  { key: "present", label: "มา" },
  { key: "late", label: "สาย" },
  { key: "absent", label: "ขาด" },
  { key: "personal_leave", label: "ลากิจ" },
  { key: "sick_leave", label: "ลาป่วย" },
];
const STATUS_LABEL = Object.fromEntries(STATUS.map((s) => [s.key, s.label]));
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
  if (btn && nav) btn.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    btn.setAttribute("aria-expanded", String(open));
  });
  const logout = document.getElementById("logout-btn");
  if (logout) logout.addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* go to login anyway */ }
    window.location.href = "/login";
  });
});

"use strict";

const PAGE = 50;
const fromEl = document.getElementById("h-from");
const toEl = document.getElementById("h-to");
const scopeEl = document.getElementById("h-scope");
const body = document.getElementById("h-body");
const table = document.getElementById("h-table");
const more = document.getElementById("h-more");
let offset = 0;

function countsText(c) {
  return STATUS.filter((s) => c[s.key]).map((s) => `${s.label} ${c[s.key]}`).join(" · ") || "-";
}

// The admin's "all teachers" view has its own recorder column.
const showTeacher = () => !!scopeEl;

function row(s) {
  const q = new URLSearchParams({ room: s.classroom_id, period: s.period_id, date: s.date });
  return h("tr", {},
    h("td", { class: "nowrap" }, thaiDate(s.date)),
    h("td", {}, s.period_no),
    h("td", { class: "nowrap" }, s.classroom),
    h("td", {}, h("div", {}, s.subject), s.topic ? h("div", { class: "muted small" }, s.topic) : null,
      s.substitute_for && !scopeEl ? h("span", { class: "badge" }, `สอนแทน ${s.substitute_for}`) : null,
      !s.is_mine && !showTeacher() ? h("div", { class: "muted small" }, `ผู้บันทึก: ${s.teacher}`) : null,
      s.edited_by ? h("div", { class: "muted small" }, `แก้ไขล่าสุดโดย ${s.edited_by} ${thaiDateTime(s.edited_at)}`) : null),
    h("td", { class: "small" }, countsText(s.counts)),
    scopeEl ? h("td", { class: "small" }, s.teacher, s.substitute_for ? h("div", { class: "muted" }, `สอนแทน ${s.substitute_for}`) : null) : null,
    h("td", {}, h("a", { href: "/?" + q, class: "btn btn-secondary btn-sm" }, "เปิด")),
  );
}

async function load(reset = true) {
  if (reset) { offset = 0; body.replaceChildren(); }
  const q = new URLSearchParams({ limit: PAGE, offset, mine: !scopeEl || scopeEl.value === "mine" });
  if (fromEl.value) q.set("date_from", fromEl.value);
  if (toEl.value) q.set("date_to", toEl.value);
  document.getElementById("h-loading").classList.remove("hidden");
  try {
    const rows = await api("/api/attendance/sessions?" + q);
    body.append(...rows.map(row));
    offset += rows.length;
    more.classList.toggle("hidden", rows.length < PAGE);
    table.classList.toggle("hidden", offset === 0);
    document.getElementById("h-empty").classList.toggle("hidden", offset > 0);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    document.getElementById("h-loading").classList.add("hidden");
  }
}

for (const el of [fromEl, toEl, scopeEl]) if (el) el.addEventListener("change", () => load());
more.addEventListener("click", () => load(false));
load();

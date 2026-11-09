"use strict";

const termEl = document.getElementById("r-term");
const roomEl = document.getElementById("r-room");
const subjEl = document.getElementById("r-subject");
const printEl = document.getElementById("r-print");
const xlsxEl = document.getElementById("r-xlsx");
const ALL = "all";
let terms = [];

async function loadOptions(year) {
  const q = year ? "?academic_year=" + year : "";
  const o = await api("/api/reports/term-options" + q);
  if (!terms.length) {
    terms = o.terms;
    fillSelect(termEl, terms, { label: (t) => `ภาคเรียนที่ ${t.label}` + (t.is_current ? " (ปัจจุบัน)" : ""), placeholder: "เลือกภาคเรียน" });
    const cur = terms.find((t) => t.is_current);
    if (cur) termEl.value = String(cur.id);
  }
  fillSelect(roomEl, [{ id: ALL, name: "ทุกห้อง" }, ...o.classrooms], { placeholder: "เลือกห้อง" });
  fillSelect(subjEl, [{ id: ALL, code: "", name: "ทุกวิชา" }, ...o.subjects], { label: (s) => s.code ? `${s.code} ${s.name}` : s.name, placeholder: "เลือกวิชา" });
}

termEl.addEventListener("change", () => {
  const t = terms.find((x) => String(x.id) === termEl.value);
  if (t) loadOptions(t.academic_year).catch((e) => toast(e.message, "error"));
});

function query() {
  const q = new URLSearchParams({ term_id: termEl.value });
  if (roomEl.value !== ALL) q.set("classroom_id", roomEl.value);
  if (subjEl.value !== ALL) q.set("subject_id", subjEl.value);
  return q;
}

function hideResults() {
  for (const id of ["r-result", "r-list"]) document.getElementById(id).classList.add("hidden");
  printEl.classList.add("hidden");
  xlsxEl.classList.add("hidden");
}
for (const el of [termEl, roomEl, subjEl]) el.addEventListener("change", hideResults);

function termLabel() {
  return termEl.selectedOptions[0]?.textContent.replace(" (ปัจจุบัน)", "") || "";
}

function showOne(r) {
  document.getElementById("r-caption").textContent =
    `${r.classroom.name} · ${r.subject.code} ${r.subject.name} · ภาคเรียนที่ ${r.term.term_no}/${r.term.academic_year} · บันทึกแล้ว ${r.sessions.length} คาบ`;
  document.getElementById("r-body").replaceChildren(...r.students.map((s) => h("tr", {},
    h("td", {}, s.number ?? "-"),
    h("td", {}, s.name),
    ...["present", "leave", "absent"].map((k) => h("td", { class: "num" }, s.counts[k])),
    h("td", { class: "num" + (s.percent !== null && s.percent < 80 ? " badge-warn" : "") }, s.percent === null ? "-" : s.percent.toFixed(1)),
  )));
  if (!r.students.length) document.getElementById("r-body").append(h("tr", {}, h("td", { colspan: "6", class: "empty" }, "ไม่มีนักเรียนในห้องนี้")));
  document.getElementById("r-result").classList.remove("hidden");
}

function showList(items) {
  const totalSessions = items.reduce((n, x) => n + x.sessions, 0);
  document.getElementById("r-list-caption").textContent = items.length
    ? `${termLabel()} · ${items.length} รายการ (ห้อง × วิชา) · บันทึกรวม ${totalSessions} คาบ · กดพิมพ์หรือดาวน์โหลด Excel เพื่อเอาออกทั้งหมดพร้อมกัน`
    : `${termLabel()} · ยังไม่มีการบันทึกการสอนตามที่เลือก`;
  document.getElementById("r-list-body").replaceChildren(...items.map((x) => {
    const q = new URLSearchParams({ term_id: termEl.value, classroom_id: x.classroom.id, subject_id: x.subject.id });
    return h("tr", {},
      h("td", { class: "nowrap" }, x.classroom.name),
      h("td", {}, `${x.subject.code} ${x.subject.name}`),
      h("td", { class: "small" }, x.teachers.join(", ")),
      h("td", { class: "num" }, x.sessions),
      h("td", { class: "num" }, x.students),
      h("td", { class: "num" + (x.low ? " badge-warn" : "") }, x.low),
      h("td", {}, h("a", { href: "/reports/term/print?" + q, target: "_blank", rel: "noopener", class: "btn btn-secondary btn-sm" }, "พิมพ์")),
    );
  }));
  document.getElementById("r-list").classList.remove("hidden");
}

document.getElementById("r-show").addEventListener("click", async (e) => {
  if (!termEl.value || !roomEl.value || !subjEl.value) { toast("กรุณาเลือกภาคเรียน ห้อง และวิชา", "error"); return; }
  const q = query();
  const many = roomEl.value === ALL || subjEl.value === ALL;
  hideResults();
  document.getElementById("r-loading").classList.remove("hidden");
  try {
    if (many) {
      const items = await withBusy(e.currentTarget, () => api("/api/reports/term-list?" + q));
      showList(items);
      if (!items.length) return;
    } else {
      showOne(await withBusy(e.currentTarget, () => api("/api/reports/term?" + q)));
    }
    printEl.href = "/reports/term/print?" + q;
    xlsxEl.href = "/api/reports/term.xlsx?" + q;
    printEl.classList.remove("hidden");
    xlsxEl.classList.remove("hidden");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    document.getElementById("r-loading").classList.add("hidden");
  }
});

loadOptions().catch((e) => toast(e.message, "error"));

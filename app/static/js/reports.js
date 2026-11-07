"use strict";

const termEl = document.getElementById("r-term");
const roomEl = document.getElementById("r-room");
const subjEl = document.getElementById("r-subject");
const printEl = document.getElementById("r-print");
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
  fillSelect(roomEl, o.classrooms, { placeholder: "เลือกห้อง" });
  fillSelect(subjEl, o.subjects, { label: (s) => `${s.code} ${s.name}`, placeholder: "เลือกวิชา" });
}

termEl.addEventListener("change", () => {
  const t = terms.find((x) => String(x.id) === termEl.value);
  if (t) loadOptions(t.academic_year).catch((e) => toast(e.message, "error"));
});

document.getElementById("r-show").addEventListener("click", async (e) => {
  if (!termEl.value || !roomEl.value || !subjEl.value) { toast("กรุณาเลือกภาคเรียน ห้อง และวิชา", "error"); return; }
  const q = new URLSearchParams({ term_id: termEl.value, classroom_id: roomEl.value, subject_id: subjEl.value });
  document.getElementById("r-loading").classList.remove("hidden");
  try {
    const r = await withBusy(e.currentTarget, () => api("/api/reports/term?" + q));
    document.getElementById("r-caption").textContent =
      `${r.classroom.name} · ${r.subject.code} ${r.subject.name} · ภาคเรียนที่ ${r.term.term_no}/${r.term.academic_year} · เช็คชื่อแล้ว ${r.sessions.length} คาบ`;
    document.getElementById("r-body").replaceChildren(...r.students.map((s) => h("tr", {},
      h("td", {}, s.number ?? "-"),
      h("td", {}, s.name),
      ...["present", "late", "absent", "personal_leave", "sick_leave"].map((k) => h("td", { class: "num" }, s.counts[k])),
      h("td", { class: "num" + (s.percent !== null && s.percent < 80 ? " badge-warn" : "") }, s.percent === null ? "-" : s.percent.toFixed(1)),
    )));
    if (!r.students.length) document.getElementById("r-body").append(h("tr", {}, h("td", { colspan: "8", class: "empty" }, "ไม่มีนักเรียนในห้องนี้")));
    printEl.href = "/reports/term/print?" + q;
    printEl.classList.remove("hidden");
    document.getElementById("r-result").classList.remove("hidden");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    document.getElementById("r-loading").classList.add("hidden");
  }
});

loadOptions().catch((e) => toast(e.message, "error"));

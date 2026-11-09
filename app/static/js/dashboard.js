"use strict";

const dateEl = document.getElementById("d-date");
const scopeEl = document.getElementById("d-scope");

function stat(value, label, cls = "") {
  return h("div", { class: "stat" }, h("div", { class: "v " + cls }, value), h("div", { class: "k" }, label));
}

const filterAbsent = tableFilter(document.getElementById("d-q"), document.getElementById("d-absent"), document.getElementById("d-count"));
const filterRooms = tableFilter(document.getElementById("d-room-q"), document.getElementById("d-rooms"));

async function load() {
  const q = new URLSearchParams({ scope: scopeEl ? scopeEl.value : "mine" });
  if (dateEl.value) q.set("day", dateEl.value);
  document.getElementById("d-loading").classList.remove("hidden");
  try {
    const d = await api("/api/reports/daily?" + q);
    if (!dateEl.value) dateEl.value = d.date;
    const p = d.people;
    document.getElementById("d-stats").replaceChildren(
      stat(d.session_count, "คาบที่บันทึกแล้ว"),
      stat(`${p.checked} / ${p.students}`, "นักเรียนที่ถูกเช็คแล้ว (คน)"),
      stat(p.present, "มาครบทุกคาบ (คน)"),
      stat(p.leave, "ลาบางคาบ/ทั้งวัน (คน)"),
      stat(p.absent, "ขาดอย่างน้อย 1 คาบ (คน)"),
      stat(d.attendance_rate === null ? "-" : d.attendance_rate + "%", "อัตราเข้าเรียนรายคาบ"),
    );

    document.getElementById("d-rooms").replaceChildren(...d.classrooms.map((r) => {
      const checked = new Set(r.checked_periods);
      return h("tr", {},
        h("td", { class: "nowrap" }, r.name),
        h("td", {}, h("div", { class: "period-dots" }, d.periods.map((p) => h("span", { class: "period-dot" + (checked.has(p) ? " done" : ""), title: "คาบ " + p }, p)))),
        h("td", { class: "num" }, r.people.checked ? `${r.people.checked} / ${r.students}` : `- / ${r.students}`),
        h("td", { class: "num" }, r.people.present),
        h("td", { class: "num" }, r.people.leave),
        h("td", { class: "num" + (r.people.absent ? " text-danger" : "") }, r.people.absent),
      );
    }));

    document.getElementById("d-absent").replaceChildren(...d.not_present.map((s) => h("tr", {},
      h("td", { class: "nowrap" }, s.classroom),
      h("td", {}, s.period_no),
      h("td", {}, s.name, h("div", { class: "muted small" }, s.student_code)),
      h("td", {}, h("span", { class: "chip chip-" + s.status }, STATUS_LABEL[s.status])),
      h("td", { class: "small" }, s.subject),
      h("td", { class: "small" }, s.note || ""),
    )));
    filterRooms();
    filterAbsent();
    document.getElementById("d-absent-table").classList.toggle("hidden", d.not_present.length === 0);
    document.getElementById("d-absent-empty").classList.toggle("hidden", d.not_present.length > 0);
    document.getElementById("d-content").classList.remove("hidden");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    document.getElementById("d-loading").classList.add("hidden");
  }
}

dateEl.addEventListener("change", load);
if (scopeEl) scopeEl.addEventListener("change", load);
load();

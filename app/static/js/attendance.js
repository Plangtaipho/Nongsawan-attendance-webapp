"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  date: $("f-date"), room: $("f-room"), period: $("f-period"), area: $("f-area"), subject: $("f-subject"),
  sub: $("f-sub"), subTeacher: $("f-sub-teacher"), topic: $("f-topic"), activity: $("f-activity"), list: $("students"), summary: $("summary"),
  sheet: $("sheet"), prompt: $("prompt"), loading: $("loading"), savebar: $("savebar"),
  save: $("save-btn"), savedInfo: $("saved-info"), noStudents: $("no-students"), warn: $("setup-warning"),
};

let students = []; // [{id, number, name, status, note}]
let readOnly = false;
let dirty = false;
let loadSeq = 0;

function remember(key, value) { try { localStorage.setItem("att." + key, value); } catch { /* private mode */ } }
function recall(key) { try { return localStorage.getItem("att." + key) || ""; } catch { return ""; } }

function currentPeriodId(periods) {
  const now = new Date();
  const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  const p = periods.find((x) => x.start <= hhmm && hhmm < x.end);
  return p ? String(p.id) : "";
}

let allSubjects = []; // [{id, code, name, area}]

// Subjects shown are those of the chosen learning area (กลุ่มสาระ).
function fillSubjects() {
  const area = els.area.value;
  fillSelect(els.subject, allSubjects.filter((s) => s.area === area), {
    label: (s) => `${s.code} ${s.name}`,
    placeholder: area ? "เลือกวิชา" : "เลือกกลุ่มสาระก่อน",
  });
  els.subject.disabled = !area;
}

// Select a subject by id, switching the learning area to match.
function setSubject(id) {
  const s = allSubjects.find((x) => String(x.id) === String(id));
  if (!s) return;
  els.area.value = s.area;
  fillSubjects();
  els.subject.value = String(s.id);
}

// Show the saved substitute (สอนแทน) state; the absent teacher may not be in the list (e.g. viewing as someone else).
function setSubstitute(id, name) {
  els.sub.checked = !!id;
  els.subTeacher.classList.toggle("hidden", !id);
  if (id && ![...els.subTeacher.options].some((o) => o.value === String(id))) {
    els.subTeacher.append(h("option", { value: String(id) }, name || "ครูท่านอื่น"));
  }
  els.subTeacher.value = id ? String(id) : "";
}

async function init() {
  let opt;
  try {
    opt = await api("/api/attendance/options");
  } catch (e) { toast(e.message, "error"); return; }

  els.date.value = opt.today;
  els.date.max = opt.today;
  fillSelect(els.room, opt.classrooms, { placeholder: "เลือกห้อง" });
  fillSelect(els.period, opt.periods, { label: (p) => `คาบ ${p.no} (${p.start}-${p.end})`, placeholder: "เลือกคาบ" });
  allSubjects = opt.subjects;
  fillSelect(els.subTeacher, opt.teachers, { placeholder: "เลือกครูที่ไม่อยู่ (สอนแทนครู...)" });
  fillSelect(els.area, opt.learning_areas.map((a) => ({ id: a, name: a })), { placeholder: "เลือกกลุ่มสาระ" });
  fillSubjects();

  const missing = [];
  if (!opt.term) missing.push("ยังไม่ได้ตั้งค่าเทอมปัจจุบัน");
  if (!opt.classrooms.length) missing.push("ยังไม่มีห้องเรียน");
  if (!opt.periods.length) missing.push("ยังไม่มีคาบเรียน");
  if (!opt.subjects.length) missing.push("ยังไม่มีรายวิชา");
  if (missing.length) {
    els.warn.textContent = missing.join(" · ") + " กรุณาให้ผู้ดูแลระบบตั้งค่าก่อนใช้งาน";
    els.warn.classList.remove("hidden");
  }

  // Opened from the history page: /?room=1&period=2&date=2026-11-09
  const qs = new URLSearchParams(location.search);
  els.room.value = qs.get("room") || recall("room");
  setSubject(recall("subject"));
  els.period.value = qs.get("period") || currentPeriodId(opt.periods);
  if (qs.get("date") && qs.get("date") <= opt.today) els.date.value = qs.get("date");
  load();
}

function counts() {
  const c = {};
  for (const s of students) c[s.status] = (c[s.status] || 0) + 1;
  return c;
}

function renderSummary() {
  const c = counts();
  els.summary.replaceChildren(
    ...STATUS.filter((s) => c[s.key] || s.key === "present").map((s) => h("span", { class: "chip chip-" + s.key }, `${s.label} ${c[s.key] || 0}`)),
  );
}

function renderStudent(st) {
  const li = h("li", { class: "student" + (st.status !== "present" ? " not-present st-" + st.status : "") });
  const group = h("div", { class: "status-group", role: "group", "aria-label": "สถานะของ " + st.name });
  for (const s of STATUS) {
    group.append(h("button", {
      type: "button",
      class: "s-" + s.key,
      "aria-pressed": String(st.status === s.key),
      disabled: readOnly,
      onclick: () => {
        st.status = s.key;
        dirty = true;
        li.replaceWith(renderStudent(st));
        renderSummary();
      },
    }, s.label));
  }
  li.append(h("div", { class: "name" }, h("span", { class: "no" }, st.number ?? "-"), " ", st.name), group);
  if (st.status !== "present" || st.note) {
    const note = h("input", { class: "note", maxlength: "255", placeholder: "หมายเหตุ (ถ้ามี)", value: st.note || "", disabled: readOnly, "aria-label": "หมายเหตุของ " + st.name });
    note.addEventListener("input", () => { st.note = note.value; dirty = true; });
    li.append(note);
  }
  return li;
}

function renderList() {
  els.list.replaceChildren(...students.map(renderStudent));
  els.noStudents.classList.toggle("hidden", students.length > 0);
  renderSummary();
}

async function load() {
  const ready = els.date.value && els.room.value && els.period.value;
  els.sheet.classList.add("hidden");
  els.savebar.classList.add("hidden");
  els.prompt.classList.toggle("hidden", !!ready);
  if (!ready) return;

  const seq = ++loadSeq;
  els.loading.classList.remove("hidden");
  try {
    const q = new URLSearchParams({ classroom_id: els.room.value, period_id: els.period.value, session_date: els.date.value });
    const data = await api("/api/attendance/session?" + q);
    if (seq !== loadSeq) return; // a newer selection is loading
    students = data.students.map((s) => ({ ...s, status: normalStatus(s.status) }));
    const s = data.session;
    readOnly = !!(s && !s.can_edit);
    els.topic.value = s?.topic || "";
    els.activity.value = s?.activity || "";
    els.topic.disabled = els.activity.disabled = els.sub.disabled = els.subTeacher.disabled = readOnly;
    setSubstitute(s?.substitute_for_id, s?.substitute_for_name);
    if (s) {
      setSubject(String(s.subject_id));
      els.savedInfo.textContent = `คาบนี้บันทึกแล้วโดย ${s.teacher_name} (${s.subject_name})` +
        (readOnly ? " · ดูได้อย่างเดียว แก้ไขได้เฉพาะผู้บันทึกหรือผู้ดูแลระบบ" : " · แก้ไขแล้วกดบันทึกอีกครั้งได้");
      els.savedInfo.classList.remove("hidden");
    } else {
      els.savedInfo.classList.add("hidden");
    }
    $("all-present").disabled = readOnly;
    dirty = false;
    renderList();
    els.sheet.classList.remove("hidden");
    els.savebar.classList.toggle("hidden", readOnly || students.length === 0);
    els.save.textContent = s ? "บันทึกการแก้ไข" : "บันทึกการเช็คชื่อ";
  } catch (e) {
    if (seq === loadSeq) toast(e.message, "error");
  } finally {
    if (seq === loadSeq) els.loading.classList.add("hidden");
  }
}

async function save() {
  if (!els.subject.value) { toast("กรุณาเลือกวิชา", "error"); els.subject.focus(); return; }
  if (els.sub.checked && !els.subTeacher.value) { toast("กรุณาเลือกครูที่สอนแทน", "error"); els.subTeacher.focus(); return; }
  const body = {
    classroom_id: Number(els.room.value),
    period_id: Number(els.period.value),
    subject_id: Number(els.subject.value),
    session_date: els.date.value,
    substitute_for_id: els.sub.checked && els.subTeacher.value ? Number(els.subTeacher.value) : null,
    topic: els.topic.value.trim() || null,
    activity: els.activity.value.trim() || null,
    records: students.map((s) => ({ student_id: s.id, status: s.status, note: (s.note || "").trim() || null })),
  };
  try {
    const res = await withBusy(els.save, () => api("/api/attendance/sessions", { method: "POST", body }));
    dirty = false;
    const c = res.counts;
    toast(`บันทึกแล้ว: ` + STATUS.filter((s) => c[s.key]).map((s) => `${s.label} ${c[s.key]}`).join(" / "), "success");
    remember("subject", els.subject.value);
    load();
  } catch (e) {
    // Keep what the teacher tapped so they can simply press save again.
    toast(e.message, "error");
  }
}

function confirmDiscard() {
  return !dirty || confirm("ยังไม่ได้บันทึกการเช็คชื่อ ต้องการเปลี่ยนโดยไม่บันทึกหรือไม่?");
}

for (const el of [els.date, els.room, els.period]) {
  let previous = el.value;
  el.addEventListener("focus", () => { previous = el.value; });
  el.addEventListener("change", () => {
    if (!confirmDiscard()) { el.value = previous; return; }
    if (el === els.room) remember("room", el.value);
    previous = el.value;
    load();
  });
}
els.subject.addEventListener("change", () => { dirty = true; });
els.area.addEventListener("change", () => { fillSubjects(); els.subject.value = ""; dirty = true; });
els.topic.addEventListener("input", () => { dirty = true; });
els.sub.addEventListener("change", () => { els.subTeacher.classList.toggle("hidden", !els.sub.checked); dirty = true; });
els.subTeacher.addEventListener("change", () => { dirty = true; });
els.activity.addEventListener("input", () => { dirty = true; });
els.save.addEventListener("click", save);
$("all-present").addEventListener("click", () => {
  for (const s of students) s.status = "present";
  dirty = true;
  renderList();
});
window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

init();

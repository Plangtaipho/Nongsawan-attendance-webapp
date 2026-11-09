"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  date: $("f-date"), room: $("f-room"), period: $("f-period"), area: $("f-area"), subject: $("f-subject"),
  sub: $("f-sub"), subTeacher: $("f-sub-teacher"), topic: $("f-topic"), activity: $("f-activity"), list: $("students"), summary: $("summary"),
  sheet: $("sheet"), prompt: $("prompt"), loading: $("loading"), savebar: $("savebar"),
  save: $("save-btn"), savedInfo: $("saved-info"), savedText: $("saved-text"), savedEdit: $("saved-edit"),
  savedActions: $("saved-actions"), savedHint: $("saved-hint"), noStudents: $("no-students"), warn: $("setup-warning"),
};

let students = []; // [{id, number, name, status, note}]
let session = null; // the saved session shown, if any
let allPeriods = [];
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

let allSubjects = []; // [{id, code, name, area, grade}]
let allRooms = []; // [{id, name, grade}]

// Subjects for the chosen room's grade (or for every grade), grouped by learning area (กลุ่มสาระ).
function roomSubjects() {
  const room = allRooms.find((r) => String(r.id) === els.room.value);
  return allSubjects.filter((s) => !s.grade || !room || s.grade === room.grade);
}

function fillAreas() {
  const present = new Set(roomSubjects().map((s) => s.area));
  const areas = [...LEARNING_AREAS, "อื่นๆ"].filter((a) => present.has(a));
  fillSelect(els.area, areas.map((a) => ({ id: a, name: a })), { placeholder: "เลือกกลุ่มสาระ" });
  fillSubjects();
}

function fillSubjects() {
  const area = els.area.value;
  fillSelect(els.subject, roomSubjects().filter((s) => s.area === area), {
    label: (s) => `${s.code} ${s.name}`,
    placeholder: area ? "เลือกวิชา" : "เลือกกลุ่มสาระก่อน",
  });
  els.subject.disabled = !area;
}

// Select a subject by id, switching the learning area to match.
function setSubject(id) {
  const s = allSubjects.find((x) => String(x.id) === String(id));
  if (!s || !roomSubjects().includes(s)) return; // a subject of another grade is not offered for this room
  fillAreas();
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
  allRooms = opt.classrooms;
  allPeriods = opt.periods;
  fillSelect($("move-period"), opt.periods, { label: (p) => `คาบ ${p.no} (${p.start}-${p.end})`, placeholder: "เลือกคาบ" });
  $("move-date").max = opt.today;
  fillSelect(els.subTeacher, opt.teachers, { placeholder: "เลือกครูที่ไม่อยู่ (สอนแทนครู...)" });
  fillAreas();

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
  fillAreas();
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
    session = s;
    readOnly = !!(s && !s.can_edit);
    els.topic.value = s?.topic || "";
    els.activity.value = s?.activity || "";
    els.topic.disabled = els.activity.disabled = els.sub.disabled = els.subTeacher.disabled = readOnly;
    setSubstitute(s?.substitute_for_id, s?.substitute_for_name);
    if (s) {
      setSubject(String(s.subject_id));
      els.savedText.textContent = `คาบนี้บันทึกแล้วโดย ${s.teacher_name} (${s.subject_name})` +
        (readOnly
          ? ` · ดูได้อย่างเดียว ถ้าคาบนี้เป็นคาบที่คุณสอน แสดงว่าอาจบันทึกผิดคาบ ให้${s.teacher_name}หรือผู้ดูแลระบบเปิดคาบนี้แล้วกด "ย้ายไปคาบอื่น"`
          : " · แก้ไขแล้วกดบันทึกอีกครั้งได้");
      els.savedEdit.textContent = s.edited_by ? `แก้ไขล่าสุดโดย ${s.edited_by} เมื่อ ${thaiDateTime(s.edited_at)}` : "";
      els.savedEdit.classList.toggle("hidden", !s.edited_by);
      els.savedActions.classList.toggle("hidden", readOnly);
      els.savedHint.classList.toggle("hidden", readOnly);
      els.savedInfo.classList.remove("hidden");
    } else {
      els.savedInfo.classList.add("hidden");
    }
    dirty = false;
    renderList();
    els.sheet.classList.remove("hidden");
    els.savebar.classList.toggle("hidden", readOnly || students.length === 0);
    els.save.textContent = s ? "บันทึกการแก้ไข" : "บันทึกการสอน";
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

function periodLabel(id) {
  const p = allPeriods.find((x) => String(x.id) === String(id));
  return p ? `คาบ ${p.no}` : "คาบ ?";
}

function openMove() {
  if (!session) return;
  if (dirty && !confirm("มีการแก้ไขที่ยังไม่ได้บันทึก ถ้าย้ายตอนนี้ การแก้ไขนั้นจะหายไป ต้องการทำต่อหรือไม่?")) return;
  $("move-from").textContent = `ตอนนี้อยู่ที่ ${periodLabel(els.period.value)} วันที่ ${thaiDate(els.date.value, false)} ห้อง ${els.room.selectedOptions[0]?.textContent || ""}`;
  $("move-date").value = els.date.value;
  $("move-period").value = "";
  $("move-dialog").showModal();
}

async function doMove(e) {
  e.preventDefault();
  const date = $("move-date").value, period = $("move-period").value;
  if (!date || !period) { toast("กรุณาเลือกวันที่และคาบที่ถูกต้อง", "error"); return; }
  try {
    const res = await withBusy($("move-ok"), () => api(`/api/attendance/sessions/${session.id}/move`, {
      method: "POST", body: { period_id: Number(period), session_date: date },
    }));
    $("move-dialog").close();
    dirty = false;
    els.date.value = res.session_date;
    els.period.value = String(res.period_id);
    toast(`ย้ายไปคาบ ${res.period_no} แล้ว`, "success");
    load();
  } catch (err) { toast(err.message, "error"); }
}

async function doDelete() {
  if (!session) return;
  const what = `${periodLabel(els.period.value)} วันที่ ${thaiDate(els.date.value, false)} (${session.subject_name})`;
  if (!confirm(`ลบบันทึกการสอน ${what} ทั้งหมด รวมข้อมูลมา/ลา/ขาดของนักเรียนทุกคน?\n\nลบแล้วกู้คืนไม่ได้`)) return;
  try {
    await withBusy($("delete-btn"), () => api(`/api/attendance/sessions/${session.id}`, { method: "DELETE" }));
    dirty = false;
    toast("ลบบันทึกแล้ว", "success");
    load();
  } catch (err) { toast(err.message, "error"); }
}

function confirmDiscard() {
  return !dirty || confirm("ยังไม่ได้บันทึกการสอน ต้องการเปลี่ยนโดยไม่บันทึกหรือไม่?");
}

for (const el of [els.date, els.room, els.period]) {
  let previous = el.value;
  el.addEventListener("focus", () => { previous = el.value; });
  el.addEventListener("change", () => {
    if (!confirmDiscard()) { el.value = previous; return; }
    if (el === els.room) {
      remember("room", el.value);
      const keep = els.subject.value; // keep the subject if the new room's grade also studies it
      fillAreas();
      if (roomSubjects().some((x) => String(x.id) === keep)) setSubject(keep);
    }
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
$("move-btn").addEventListener("click", openMove);
$("move-form").addEventListener("submit", doMove);
$("move-cancel").addEventListener("click", () => $("move-dialog").close());
$("delete-btn").addEventListener("click", doDelete);
window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

init();

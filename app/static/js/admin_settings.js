"use strict";

// One generic table + dialog, driven by a config per tab.
const $ = (id) => document.getElementById(id);
const yesNo = (v) => h("span", { class: "badge" + (v ? " badge-ok" : "") }, v ? "ใช้งาน" : "ปิด");
const hhmm = (t) => (t || "").slice(0, 5);

const TABS = {
  users: {
    title: "บัญชีครู",
    hint: "ครูใช้ชื่อผู้ใช้และรหัสผ่านที่ตั้งที่นี่เพื่อเข้าสู่ระบบ ปิดบัญชีแทนการลบ เพื่อเก็บประวัติการบันทึกการสอน",
    list: "/api/admin/users",
    url: (id) => (id ? `/api/admin/users/${id}` : "/api/admin/users"),
    updateMethod: "PATCH",
    columns: [["ชื่อ - สกุล", (u) => u.full_name], ["ชื่อผู้ใช้", (u) => u.username], ["สิทธิ์", (u) => (u.role === "admin" ? "ผู้ดูแลระบบ" : "ครู")], ["สถานะ", (u) => yesNo(u.is_active)]],
    fields: (u) => [
      { key: "full_name", label: "ชื่อ - สกุล", required: true, max: 150 },
      u ? null : { key: "username", label: "ชื่อผู้ใช้ (ภาษาอังกฤษ/ตัวเลข)", required: true, max: 50 },
      { key: "email", label: "อีเมล (ถ้ามี)", type: "email", max: 255 },
      { key: "role", label: "สิทธิ์", type: "select", options: [["teacher", "ครู"], ["admin", "ผู้ดูแลระบบ"]] },
      u ? { key: "is_active", label: "สถานะ", type: "select", options: [["true", "ใช้งาน"], ["false", "ปิดบัญชี"]] } : null,
      u ? { key: "new_password", label: "ตั้งรหัสผ่านใหม่ (เว้นว่างถ้าไม่เปลี่ยน)", type: "password" }
        : { key: "password", label: "รหัสผ่านเริ่มต้น (อย่างน้อย 8 ตัวอักษร)", type: "password", required: true },
    ],
  },
  terms: {
    title: "ภาคเรียน",
    hint: "ตั้งช่วงวันที่ของแต่ละเทอม ระบบใช้วันที่บันทึกการสอนเพื่อจัดเข้าเทอมอัตโนมัติ ต้องมีเทอมปัจจุบัน 1 เทอม",
    list: "/api/admin/terms",
    url: (id) => (id ? `/api/admin/terms/${id}` : "/api/admin/terms"),
    updateMethod: "PUT",
    columns: [["ภาคเรียน", (t) => `${t.term_no}/${t.academic_year}`], ["เริ่ม", (t) => thaiDate(t.start_date, false)], ["สิ้นสุด", (t) => thaiDate(t.end_date, false)], ["", (t) => (t.is_current ? h("span", { class: "badge badge-ok" }, "เทอมปัจจุบัน") : "")]],
    fields: () => [
      { key: "academic_year", label: "ปีการศึกษา (พ.ศ.)", type: "number", required: true, min: 2500, max: 2700 },
      { key: "term_no", label: "ภาคเรียนที่", type: "select", options: [["1", "1"], ["2", "2"], ["3", "3 (ภาคฤดูร้อน)"]] },
      { key: "start_date", label: "วันเริ่มเทอม", type: "date", required: true },
      { key: "end_date", label: "วันสิ้นสุดเทอม", type: "date", required: true },
      { key: "is_current", label: "เป็นเทอมปัจจุบัน", type: "select", options: [["true", "ใช่"], ["false", "ไม่ใช่"]] },
    ],
  },
  classrooms: {
    title: "ห้องเรียน",
    hint: "ห้องผูกกับปีการศึกษา (แสดงปีปัจจุบัน) ห้องจะถูกสร้างอัตโนมัติเมื่อนำเข้ารายชื่อนักเรียน",
    list: "/api/admin/classrooms",
    url: (id) => (id ? `/api/admin/classrooms/${id}` : "/api/admin/classrooms"),
    updateMethod: "PUT",
    columns: [["ห้อง", (c) => c.name], ["ปีการศึกษา", (c) => c.academic_year], ["สถานะ", (c) => yesNo(c.is_active)]],
    fields: () => [
      { key: "academic_year", label: "ปีการศึกษา (พ.ศ.)", type: "number", required: true, min: 2500, max: 2700 },
      { key: "grade_level", label: "ระดับชั้น (เช่น ม.1)", required: true, max: 20 },
      { key: "room_no", label: "ห้องที่ (เช่น 1)", required: true, max: 10 },
      { key: "is_active", label: "สถานะ", type: "select", options: [["true", "ใช้งาน"], ["false", "ปิด"]] },
    ],
  },
  subjects: {
    title: "รายวิชา",
    hint: "วิชาที่ปิดจะไม่แสดงในหน้าบันทึกการสอน แต่ยังอยู่ในรายงานย้อนหลัง",
    list: "/api/admin/subjects",
    url: (id) => (id ? `/api/admin/subjects/${id}` : "/api/admin/subjects"),
    updateMethod: "PUT",
    columns: [["รหัสวิชา", (s) => s.subject_code], ["ชื่อวิชา", (s) => s.name], ["ชั้น", (s) => s.grade_level || "ทุกชั้น"], ["กลุ่มสาระ", (s) => s.learning_area || "-"], ["สถานะ", (s) => yesNo(s.is_active)]],
    fields: () => [
      { key: "subject_code", label: "รหัสวิชา", required: true, max: 20 },
      { key: "name", label: "ชื่อวิชา", required: true, max: 150 },
      { key: "learning_area", label: "กลุ่มสาระการเรียนรู้", type: "select", options: [["", "อัตโนมัติจากรหัสวิชา"], ...LEARNING_AREAS.map((a) => [a, a])] },
      { key: "grade_level", label: "ชั้นที่เรียนวิชานี้", type: "select", options: [["", "ทุกชั้น"], ...["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6"].map((g) => [g, g])] },
      { key: "is_active", label: "สถานะ", type: "select", options: [["true", "ใช้งาน"], ["false", "ปิด"]] },
    ],
  },
  periods: {
    title: "คาบเรียน",
    hint: "เวลาคาบใช้เลือกคาบปัจจุบันให้อัตโนมัติในหน้าบันทึกการสอน",
    list: "/api/admin/periods",
    url: (id) => (id ? `/api/admin/periods/${id}` : "/api/admin/periods"),
    updateMethod: "PUT",
    deletable: true,
    columns: [["คาบที่", (p) => p.period_no], ["เวลา", (p) => `${hhmm(p.start_time)} - ${hhmm(p.end_time)}`]],
    fields: () => [
      { key: "period_no", label: "คาบที่", type: "number", required: true, min: 1, max: 20 },
      { key: "start_time", label: "เวลาเริ่ม", type: "time", required: true },
      { key: "end_time", label: "เวลาสิ้นสุด", type: "time", required: true },
    ],
  },
};

let tab = "users";
let editing = null;
let currentFields = [];
let defaultYear = new Date().getFullYear() + 543;

async function load() {
  const cfg = TABS[tab];
  $("tab-hint").textContent = cfg.hint;
  $("t-head").replaceChildren(h("tr", {}, cfg.columns.map(([label]) => h("th", {}, label)), h("th", {})));
  $("t-body").replaceChildren();
  $("loading").classList.remove("hidden");
  try {
    const rows = await api(cfg.list);
    $("t-body").replaceChildren(...rows.map((r) => h("tr", {},
      cfg.columns.map(([, fn]) => h("td", {}, fn(r))),
      h("td", { class: "nowrap" },
        h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => openDialog(r) }, "แก้ไข"),
        cfg.deletable ? h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => remove(r) }, "ลบ") : null),
    )));
    $("t-empty").classList.toggle("hidden", rows.length > 0);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    $("loading").classList.add("hidden");
  }
}

function openDialog(row = null) {
  const cfg = TABS[tab];
  editing = row;
  currentFields = cfg.fields(row).filter(Boolean);
  $("dlg-title").textContent = (row ? "แก้ไข" : "เพิ่ม") + cfg.title;
  const defaults = { academic_year: defaultYear, is_active: true, is_current: false, role: "teacher", term_no: 1 };
  $("dlg-fields").replaceChildren(...currentFields.map((f) => {
    const id = "fld-" + f.key;
    let v = row ? row[f.key] : defaults[f.key];
    if (f.type === "time") v = hhmm(v);
    let input;
    if (f.type === "select") {
      input = h("select", { id }, f.options.map(([val, label]) => h("option", { value: val }, label)));
      if (v !== undefined && v !== null) input.value = String(v);
    } else {
      input = h("input", { id, type: f.type || "text", maxlength: f.max, min: f.min, max: f.type === "number" ? f.max : null, required: f.required, autocomplete: f.type === "password" ? "new-password" : "off" });
      if (f.type === "number") input.removeAttribute("maxlength");
      input.value = v ?? "";
    }
    return h("div", { class: "field" }, h("label", { for: id }, f.label), input);
  }));
  $("dlg").showModal();
}


function readForm() {
  const body = {};
  for (const f of currentFields) {
    const raw = $("fld-" + f.key).value.trim();
    if (f.required && !raw) { toast(`กรุณากรอก ${f.label}`, "error"); return null; }
    if (f.type === "number") body[f.key] = Number(raw);
    else if (f.type === "select" && (raw === "true" || raw === "false")) body[f.key] = raw === "true";
    else if (f.key === "term_no") body[f.key] = Number(raw);
    else if (f.type === "password" && !raw) continue;
    else if (f.key === "grade_level" && tab === "subjects") body[f.key] = raw; // "" = every grade
    else body[f.key] = raw || null;
  }
  return body;
}

$("dlg-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = readForm();
  if (!body) return;
  const cfg = TABS[tab];
  try {
    await withBusy(e.submitter, () => api(cfg.url(editing?.id), { method: editing ? cfg.updateMethod : "POST", body }));
    $("dlg").close();
    toast("บันทึกแล้ว", "success");
    load();
  } catch (err) {
    toast(err.message, "error");
  }
});

async function remove(row) {
  if (!confirm("ยืนยันการลบ?")) return;
  try {
    await api(TABS[tab].url(row.id), { method: "DELETE" });
    toast("ลบแล้ว", "success");
    load();
  } catch (e) { toast(e.message, "error"); }
}

$("dlg-cancel").addEventListener("click", () => $("dlg").close());
$("add-btn").addEventListener("click", () => openDialog());
for (const b of document.querySelectorAll("[data-tab]")) {
  b.addEventListener("click", () => {
    tab = b.dataset.tab;
    for (const x of document.querySelectorAll("[data-tab]")) x.setAttribute("aria-selected", String(x === b));
    load();
  });
}

api("/api/attendance/options").then((o) => { defaultYear = o.academic_year; }).catch(() => {});
load();

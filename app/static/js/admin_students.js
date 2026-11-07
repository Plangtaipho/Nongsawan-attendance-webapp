"use strict";

const $ = (id) => document.getElementById(id);
const STUDENT_STATUS = { active: "กำลังศึกษา", transferred: "ย้ายออก", graduated: "จบการศึกษา", inactive: "พักการเรียน/อื่นๆ" };
let rooms = [];
let editing = null; // student being edited, or null when adding

// ---------- Student list ----------
async function loadRooms() {
  rooms = await api("/api/admin/classrooms");
  fillSelect($("s-room"), rooms, { placeholder: "ทุกห้อง" });
  fillSelect($("sf-room"), rooms, { placeholder: "เลือกห้อง" });
}

async function loadStudents() {
  const q = new URLSearchParams();
  if ($("s-room").value) q.set("classroom_id", $("s-room").value);
  if ($("s-q").value.trim()) q.set("q", $("s-q").value.trim());
  $("s-loading").classList.remove("hidden");
  try {
    const list = await api("/api/admin/students?" + q);
    $("s-body").replaceChildren(...list.map((s) => h("tr", {},
      h("td", { class: "nowrap" }, s.classroom_name || "-"),
      h("td", {}, s.class_number ?? "-"),
      h("td", {}, s.student_code),
      h("td", {}, s.full_name),
      h("td", {}, h("span", { class: "badge" + (s.status === "active" ? " badge-ok" : "") }, STUDENT_STATUS[s.status])),
      h("td", {}, h("button", { class: "btn btn-secondary btn-sm", type: "button", onclick: () => openDialog(s) }, "แก้ไข")),
    )));
    $("s-empty").classList.toggle("hidden", list.length > 0);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    $("s-loading").classList.add("hidden");
  }
}

function openDialog(s = null) {
  editing = s;
  $("s-dialog-title").textContent = s ? "แก้ไขข้อมูลนักเรียน" : "เพิ่มนักเรียน";
  $("sf-code").value = s?.student_code || "";
  $("sf-prefix").value = s?.prefix || "";
  $("sf-first").value = s?.first_name || "";
  $("sf-last").value = s?.last_name || "";
  $("sf-room").value = s?.classroom_id ? String(s.classroom_id) : $("s-room").value;
  $("sf-number").value = s?.class_number ?? "";
  $("sf-status").value = s?.status || "active";
  $("sf-status-wrap").classList.toggle("hidden", !s);
  $("s-dialog").showModal();
}

$("s-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    student_code: $("sf-code").value.trim(),
    prefix: $("sf-prefix").value.trim(),
    first_name: $("sf-first").value.trim(),
    last_name: $("sf-last").value.trim(),
    classroom_id: Number($("sf-room").value) || null,
    class_number: $("sf-number").value ? Number($("sf-number").value) : null,
  };
  if (!body.student_code || !body.prefix || !body.first_name || !body.last_name || !body.classroom_id) {
    toast("กรุณากรอกข้อมูลให้ครบ และเลือกห้อง", "error");
    return;
  }
  try {
    await withBusy(e.submitter, () => editing
      ? api(`/api/admin/students/${editing.id}`, { method: "PATCH", body: { ...body, status: $("sf-status").value } })
      : api("/api/admin/students", { method: "POST", body }));
    $("s-dialog").close();
    toast("บันทึกแล้ว", "success");
    loadStudents();
  } catch (err) {
    toast(err.message, "error");
  }
});
$("s-cancel").addEventListener("click", () => $("s-dialog").close());
$("add-student").addEventListener("click", () => openDialog());
$("s-room").addEventListener("change", loadStudents);
let searchTimer;
$("s-q").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadStudents, 300); });

// ---------- Excel import ----------
function importForm() {
  const file = $("imp-file").files[0];
  const year = $("imp-year").value;
  if (!file) { toast("กรุณาเลือกไฟล์ .xlsx", "error"); return null; }
  if (!/\.xlsx$/i.test(file.name)) { toast("รองรับเฉพาะไฟล์ .xlsx", "error"); return null; }
  if (file.size > 2 * 1024 * 1024) { toast("ไฟล์ใหญ่เกิน 2 MB", "error"); return null; }
  if (!year) { toast("กรุณาระบุปีการศึกษา", "error"); return null; }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("academic_year", year);
  return fd;
}

$("imp-preview").addEventListener("click", async (e) => {
  const fd = importForm();
  if (!fd) return;
  $("imp-commit").classList.add("hidden");
  try {
    const p = await withBusy(e.currentTarget, () => api("/api/admin/students/import/preview", { method: "POST", form: fd }));
    const summary = $("imp-summary");
    const parts = [`ทั้งหมด ${p.total} แถว`, `เพิ่มใหม่ ${p.new_count}`, `อัปเดต ${p.update_count}`];
    if (p.new_classrooms.length) parts.push(`สร้างห้องใหม่: ${p.new_classrooms.join(", ")}`);
    if (p.rooms && p.rooms.length) parts.push(`แยกห้อง: ${p.rooms.map((r) => `${r.name} (${r.count})`).join(", ")}`);
    if (p.error_count) parts.push(`ผิดพลาด ${p.error_count} แถว (แก้ไฟล์แล้วตรวจสอบใหม่)`);
    summary.textContent = parts.join(" · ");
    summary.className = "alert " + (p.error_count ? "alert-error" : "alert-info");
    // Errors first, so they are easy to find in long files.
    const rows = p.rows.map((r, i) => ({ ...r, i })).sort((a, b) => (b.errors.length > 0) - (a.errors.length > 0) || a.i - b.i);
    $("imp-body").replaceChildren(...rows.map((r) => h("tr", { class: r.errors.length ? "row-error" : "" },
      h("td", { class: "nowrap" }, r.sheet ? `${r.sheet}: ${r.row_no}` : r.row_no),
      h("td", {}, r.student_code),
      h("td", {}, `${r.prefix}${r.first_name} ${r.last_name}`),
      h("td", { class: "nowrap" }, r.grade_level && r.room_no ? `${r.grade_level}/${r.room_no}` : "-"),
      h("td", {}, r.class_number ?? "-"),
      h("td", { class: "small" }, r.errors.length ? r.errors.join(", ") : (r.action === "new" ? "เพิ่มใหม่" : "อัปเดต")),
    )));
    $("imp-result").classList.remove("hidden");
    $("imp-commit").classList.toggle("hidden", p.error_count > 0);
  } catch (err) {
    toast(err.message, "error");
  }
});

$("imp-commit").addEventListener("click", async (e) => {
  const fd = importForm();
  if (!fd) return;
  if (!confirm("ยืนยันนำเข้ารายชื่อนักเรียนตามไฟล์นี้?")) return;
  try {
    const r = await withBusy(e.currentTarget, () => api("/api/admin/students/import/commit", { method: "POST", form: fd }));
    toast(`นำเข้าแล้ว: เพิ่มใหม่ ${r.created} คน, อัปเดต ${r.updated} คน, สร้างห้อง ${r.created_classrooms} ห้อง`, "success");
    $("imp-commit").classList.add("hidden");
    $("imp-result").classList.add("hidden");
    $("imp-file").value = "";
    await loadRooms();
    loadStudents();
  } catch (err) {
    toast(err.message, "error");
  }
});
$("imp-file").addEventListener("change", () => { $("imp-commit").classList.add("hidden"); $("imp-result").classList.add("hidden"); });

(async () => {
  try {
    const opt = await api("/api/attendance/options");
    $("imp-year").value = opt.academic_year;
    await loadRooms();
    loadStudents();
  } catch (e) { toast(e.message, "error"); }
})();

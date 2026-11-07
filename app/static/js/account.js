"use strict";

document.getElementById("pw-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const cur = document.getElementById("pw-current").value;
  const nw = document.getElementById("pw-new").value;
  const cf = document.getElementById("pw-confirm").value;
  if (nw.length < 8) return toast("รหัสผ่านใหม่ต้องมีอย่างน้อย 8 ตัวอักษร", "error");
  if (nw !== cf) return toast("ยืนยันรหัสผ่านไม่ตรงกัน", "error");
  try {
    await withBusy(e.submitter, () => api("/api/auth/change-password", { method: "POST", body: { current_password: cur, new_password: nw } }));
    e.target.reset();
    toast("เปลี่ยนรหัสผ่านแล้ว", "success");
  } catch (err) {
    toast(err.message, "error");
  }
});

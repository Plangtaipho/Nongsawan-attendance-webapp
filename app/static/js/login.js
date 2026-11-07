"use strict";

function safeNext() {
  // Only allow local paths, so the login page cannot be used to redirect to another site.
  const next = new URLSearchParams(location.search).get("next") || "/";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

// Carry ?next= through the Google sign-in so teachers land where they were going.
const googleLink = document.getElementById("google-login");
if (googleLink) googleLink.href = "/auth/google/start?next=" + encodeURIComponent(safeNext());

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errBox = document.getElementById("login-error");
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  errBox.classList.add("hidden");
  if (!username || !password) {
    errBox.textContent = "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน";
    errBox.classList.remove("hidden");
    return;
  }
  const btn = e.submitter || e.target.querySelector("button");
  try {
    await withBusy(btn, () => api("/api/auth/login", { method: "POST", body: { username, password } }));
    window.location.href = safeNext();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
});

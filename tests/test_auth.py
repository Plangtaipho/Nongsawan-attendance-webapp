from tests.conftest import PASSWORD, Api


def test_login_success_and_me(seed):
    a = Api("teacher1")
    r = a.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "teacher1"
    assert "password_hash" not in r.json()


def test_login_wrong_password(seed):
    r = Api().login("teacher1", "wrong-pass")
    assert r.status_code == 401
    assert r.json()["detail"] == "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"


def test_unknown_user_same_message(seed):
    r = Api().login("nobody", "whatever1")
    assert r.status_code == 401
    assert r.json()["detail"] == "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"


def test_rate_limit_after_five_failures(seed):
    a = Api()
    for _ in range(5):
        assert a.login("teacher1", "wrong-pass").status_code == 401
    r = a.login("teacher1", PASSWORD)  # even the right password is blocked now
    assert r.status_code == 429


def test_inactive_user_cannot_login(seed):
    admin = Api("admin")
    assert admin.patch(f"/api/admin/users/{seed['t1']}", json={"is_active": False}).status_code == 200
    assert Api().login("teacher1", PASSWORD).status_code == 401


def test_api_requires_login(seed):
    assert Api().get("/api/attendance/options").status_code == 401


def test_pages_redirect_to_login(seed):
    r = Api().get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_csrf_required_for_changes(seed):
    a = Api("teacher1")
    r = a.c.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "newpass123"})
    assert r.status_code == 403


def test_change_password(seed):
    a = Api("teacher1")
    assert a.post("/api/auth/change-password", json={"current_password": "bad", "new_password": "newpass123"}).status_code == 400
    assert a.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"}).status_code == 422
    assert a.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "newpass123"}).status_code == 204
    assert Api().login("teacher1", "newpass123").status_code == 200


def test_logout(seed):
    a = Api("teacher1")
    assert a.post("/api/auth/logout").status_code == 204
    assert a.get("/api/auth/me").status_code == 401


def test_teacher_cannot_use_admin_api(seed):
    a = Api("teacher1")
    assert a.get("/api/admin/users").status_code == 403
    r = a.get("/admin/settings", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_security_headers(seed):
    r = Api().get("/login")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]

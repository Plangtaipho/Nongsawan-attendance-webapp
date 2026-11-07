from io import BytesIO

from openpyxl import Workbook

from tests.conftest import PASSWORD, Api


def xlsx(rows, headers=("เลขประจำตัว", "คำนำหน้า", "ชื่อ", "นามสกุล", "ชั้น", "ห้อง", "เลขที่"), title_row=False) -> bytes:
    wb = Workbook()
    ws = wb.active
    if title_row:
        ws.append(["รายชื่อนักเรียน ปีการศึกษา 2569"])
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(a, path, data, year, name="students.xlsx"):
    return a.post(path, files={"file": (name, data, "application/octet-stream")}, data={"academic_year": str(year)})


def test_create_teacher_and_login(seed):
    a = Api("admin")
    r = a.post("/api/admin/users", json={"username": "teacher3", "full_name": "ครูสาม", "password": "password999"})
    assert r.status_code == 201
    assert a.post("/api/admin/users", json={"username": "teacher3", "full_name": "ซ้ำ", "password": "password999"}).status_code == 409
    assert Api().login("teacher3", "password999").status_code == 200


def test_admin_cannot_lock_self_out(seed):
    a = Api("admin")
    me = a.get("/api/auth/me").json()
    assert a.patch(f"/api/admin/users/{me['id']}", json={"is_active": False}).status_code == 400


def test_reset_password(seed):
    a = Api("admin")
    assert a.patch(f"/api/admin/users/{seed['t1']}", json={"new_password": "resetpass1"}).status_code == 200
    assert Api().login("teacher1", PASSWORD).status_code == 401
    assert Api().login("teacher1", "resetpass1").status_code == 200


def test_term_current_is_exclusive_and_no_overlap(seed):
    a = Api("admin")
    year = seed["today"].year + 543
    r = a.post("/api/admin/terms", json={"academic_year": year + 1, "term_no": 1, "start_date": "2099-05-16", "end_date": "2099-10-10", "is_current": True})
    assert r.status_code == 201
    terms = a.get("/api/admin/terms").json()
    assert [t["is_current"] for t in terms].count(True) == 1
    overlap = a.post("/api/admin/terms", json={"academic_year": year + 1, "term_no": 2, "start_date": "2099-10-01", "end_date": "2099-12-31"})
    assert overlap.status_code == 409


def test_import_preview_flags_errors(seed):
    a = Api("admin")
    data = xlsx([
        ("30001", "ด.ช.", "เอ", "หนึ่ง", "ม.2", "1", 1),
        ("30001", "ด.ญ.", "บี", "สอง", "ม.2", "1", 2),  # duplicate code
        ("30003", "", "ซี", "สาม", "ม.2", "1", "x"),  # no prefix, bad number
        ("10001", "ด.ช.", "ก้อง", "ใจดี(แก้)", "ม.1", "1", 1),  # existing student
    ])
    r = upload(a, "/api/admin/students/import/preview", data, seed["today"].year + 543)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["total"] == 4 and p["error_count"] == 2
    assert p["new_count"] == 1 and p["update_count"] == 1
    assert p["new_classrooms"] == ["ม.2/1"]
    # Commit is refused while errors remain.
    assert upload(a, "/api/admin/students/import/commit", data, seed["today"].year + 543).status_code == 400


def test_import_commit_creates_rooms_and_moves_students(seed):
    a = Api("admin")
    year = seed["today"].year + 543
    data = xlsx(
        [
            ("30001", "ด.ช.", "เอ", "หนึ่ง", "ม.2", "1", 1),
            ("10001", "ด.ช.", "ก้อง", "ใจดี", "ม.1", "2", 5),  # moves from ม.1/1 to ม.1/2
        ],
        title_row=True,
    )
    r = upload(a, "/api/admin/students/import/commit", data, year)
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 1, "updated": 1, "created_classrooms": 1}
    rooms = {c["name"]: c["id"] for c in a.get("/api/admin/classrooms").json()}
    in_12 = a.get("/api/admin/students", params={"classroom_id": rooms["ม.1/2"]}).json()
    assert {s["student_code"]: s["class_number"] for s in in_12} == {"20001": 1, "10001": 5}
    in_11 = a.get("/api/admin/students", params={"classroom_id": rooms["ม.1/1"]}).json()
    assert "10001" not in {s["student_code"] for s in in_11}


def test_import_rejects_non_xlsx_and_missing_header(seed):
    a = Api("admin")
    assert upload(a, "/api/admin/students/import/preview", b"a,b,c", 2569, name="x.csv").status_code == 400
    bad = xlsx([("1", "2")], headers=("foo", "bar"))
    r = upload(a, "/api/admin/students/import/preview", bad, 2569)
    assert r.status_code == 400 and "หัวตาราง" in r.json()["detail"]
    junk = upload(a, "/api/admin/students/import/preview", b"not really excel", 2569)
    assert junk.status_code == 400


def test_template_download_is_importable(seed):
    a = Api("admin")
    r = a.get("/api/admin/students/import/template")
    assert r.status_code == 200
    p = upload(a, "/api/admin/students/import/preview", r.content, 2569).json()
    assert p["total"] == 2 and p["error_count"] == 0


def test_add_and_edit_single_student(seed):
    a = Api("admin")
    r = a.post("/api/admin/students", json={"student_code": "40001", "prefix": "ด.ญ.", "first_name": "ใหม่", "last_name": "มาเพิ่ม", "classroom_id": seed["room_id"], "class_number": 4})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["classroom_name"] == "ม.1/1"
    assert a.post("/api/admin/students", json={"student_code": "40001", "prefix": "ด.ญ.", "first_name": "x", "last_name": "y", "classroom_id": seed["room_id"]}).status_code == 409
    r = a.patch(f"/api/admin/students/{sid}", json={"status": "transferred"})
    assert r.status_code == 200 and r.json()["status"] == "transferred"
    # Transferred students drop off the attendance list.
    names = [s["code"] for s in Api("teacher1").get(
        "/api/attendance/session",
        params={"classroom_id": seed["room_id"], "period_id": seed["p1"], "session_date": seed["today"].isoformat()},
    ).json()["students"]]
    assert "40001" not in names


def test_period_delete_blocked_when_used(seed):
    from tests.conftest import session_body

    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed))
    a = Api("admin")
    assert a.delete(f"/api/admin/periods/{seed['p1']}").status_code == 409
    assert a.delete(f"/api/admin/periods/{seed['p2']}").status_code == 204

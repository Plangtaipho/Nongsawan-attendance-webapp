from tests.conftest import Api, session_body


def test_daily_dashboard(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "personal_leave")))
    Api("teacher2").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "personal_leave", "present"), period="p2"))

    mine = Api("teacher1").get("/api/reports/daily").json()
    assert mine["session_count"] == 1
    assert mine["totals"]["absent"] == 1

    school = Api("admin").get("/api/reports/daily", params={"scope": "all"}).json()
    assert school["session_count"] == 2
    assert school["totals"] == {"present": 3, "leave": 2, "absent": 1}
    assert school["attendance_rate"] == 50.0
    room = next(c for c in school["classrooms"] if c["name"] == "ม.1/1")
    assert sorted(room["checked_periods"]) == [1, 2]
    assert len(school["not_present"]) == 3  # absent + two on leave
    assert {x["status"] for x in school["not_present"]} == {"absent", "leave"}

    # A teacher asking for scope=all still only gets their own.
    assert Api("teacher2").get("/api/reports/daily", params={"scope": "all"}).json()["session_count"] == 1


def test_term_report_counts_and_percent(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "present")))
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "personal_leave"), period="p2"))
    r = Api("teacher2").get(
        "/api/reports/term", params={"term_id": seed["term_id"], "classroom_id": seed["room_id"], "subject_id": seed["subject_id"]}
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["sessions"]) == 2
    s1, s2, s3 = data["students"]
    assert s1["percent"] == 100.0 and s1["statuses"] == ["present", "present"]
    assert s2["percent"] == 0.0 and s2["counts"]["absent"] == 2
    assert s3["percent"] == 50.0 and s3["counts"] == {"present": 1, "leave": 1, "absent": 0}  # leave is not attendance
    assert s3["statuses"] == ["present", "leave"]


def test_print_page_renders_thai(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed))
    r = Api("teacher1").get(
        "/reports/term/print", params={"term_id": seed["term_id"], "classroom_id": seed["room_id"], "subject_id": seed["subject_id"]}
    )
    assert r.status_code == 200
    assert "คณิตศาสตร์ 1" in r.text and "ด.ช.ก้อง ใจดี" in r.text and "สมการเชิงเส้น" in r.text


def test_report_404_for_bad_ids(seed):
    r = Api("teacher1").get("/api/reports/term", params={"term_id": 999, "classroom_id": seed["room_id"], "subject_id": seed["subject_id"]})
    assert r.status_code == 404


def _two_rooms(seed):
    """Room 1 gets two checks; room 2 (one student) gets one."""
    t1 = Api("teacher1")
    t1.post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "present")))
    t1.post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "personal_leave"), period="p2"))
    other = session_body(seed, statuses=("absent",))
    other.update(classroom_id=seed["other_room_id"], records=[{"student_id": seed["outsider"], "status": "absent"}])
    assert t1.post("/api/attendance/sessions", json=other).status_code == 200


def test_term_list_all_rooms(seed):
    _two_rooms(seed)
    a = Api("teacher2")
    items = a.get("/api/reports/term-list", params={"term_id": seed["term_id"], "subject_id": seed["subject_id"]}).json()
    assert [(x["classroom"]["name"], x["sessions"], x["students"]) for x in items] == [("ม.1/1", 2, 3), ("ม.1/2", 1, 1)]
    assert items[0]["teachers"] == ["ครูหนึ่ง"] and items[1]["low"] == 1
    # Every room and every subject.
    assert len(a.get("/api/reports/term-list", params={"term_id": seed["term_id"]}).json()) == 2


def test_print_all_rooms(seed):
    _two_rooms(seed)
    html = Api("teacher2").get("/reports/term/print", params={"term_id": seed["term_id"]}).text
    assert "ชั้น ม.1/1" in html and "ชั้น ม.1/2" in html and "2 รายการ" in html


def test_xlsx_all_rooms(seed):
    import io

    from openpyxl import load_workbook

    _two_rooms(seed)
    r = Api("teacher2").get("/api/reports/term.xlsx", params={"term_id": seed["term_id"]})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"] and ".xlsx" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["สรุป", "ม.1-1 ค21101", "ม.1-2 ค21101", "หัวข้อการสอน"]
    ws = wb["ม.1-1 ค21101"]
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=7, max_row=9)]
    # เลขที่, code, name, 2 periods, มา ลา ขาด ร้อยละ
    assert rows[1][3:] == ["ข", "ข", 0, 0, 2, 0.0]
    assert rows[2][3:] == ["/", "ล", 1, 1, 0, 50.0]
    assert wb["สรุป"]["A4"].value == "ม.1/1" and wb["สรุป"]["E4"].value == 2
    assert wb["หัวข้อการสอน"].max_row == 4  # header + 3 checks


def test_xlsx_single_room_with_no_checks(seed):
    r = Api("teacher1").get(
        "/api/reports/term.xlsx", params={"term_id": seed["term_id"], "classroom_id": seed["room_id"], "subject_id": seed["subject_id"]}
    )
    assert r.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["สรุป", "ม.1-1 ค21101", "หัวข้อการสอน"]
    assert Api("teacher1").get("/api/reports/term.xlsx", params={"term_id": 9999}).status_code == 404

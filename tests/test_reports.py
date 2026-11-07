from tests.conftest import Api, session_body


def test_daily_dashboard(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "late")))
    Api("teacher2").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "sick_leave", "present"), period="p2"))

    mine = Api("teacher1").get("/api/reports/daily").json()
    assert mine["session_count"] == 1
    assert mine["totals"]["absent"] == 1

    school = Api("admin").get("/api/reports/daily", params={"scope": "all"}).json()
    assert school["session_count"] == 2
    assert school["totals"] == {"present": 3, "late": 1, "absent": 1, "personal_leave": 0, "sick_leave": 1}
    assert school["attendance_rate"] == round(100 * 4 / 6, 1)
    room = next(c for c in school["classrooms"] if c["name"] == "ม.1/1")
    assert sorted(room["checked_periods"]) == [1, 2]
    assert len(school["not_present"]) == 3  # absent, late, sick leave

    # A teacher asking for scope=all still only gets their own.
    assert Api("teacher2").get("/api/reports/daily", params={"scope": "all"}).json()["session_count"] == 1


def test_term_report_counts_and_percent(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "late")))
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
    assert s3["percent"] == 50.0  # late counts as attended, leave does not


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

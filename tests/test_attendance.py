from datetime import timedelta

from tests.conftest import Api, session_body


def test_options_lists_dropdowns(seed):
    r = Api("teacher1").get("/api/attendance/options")
    assert r.status_code == 200
    data = r.json()
    assert [c["name"] for c in data["classrooms"]] == ["ม.1/1", "ม.1/2"]
    assert len(data["periods"]) == 2 and data["term"]["term_no"] == 2


def test_new_session_defaults_everyone_present(seed):
    r = Api("teacher1").get(
        "/api/attendance/session",
        params={"classroom_id": seed["room_id"], "period_id": seed["p1"], "session_date": seed["today"].isoformat()},
    )
    data = r.json()
    assert data["session"] is None
    assert [s["number"] for s in data["students"]] == [1, 2, 3]
    assert {s["status"] for s in data["students"]} == {"present"}


def test_save_then_reload(seed):
    a = Api("teacher1")
    r = a.post("/api/attendance/sessions", json=session_body(seed))
    assert r.status_code == 200, r.text
    assert r.json()["created"] is True
    assert r.json()["counts"] == {"present": 1, "absent": 1, "personal_leave": 1}

    data = a.get(
        "/api/attendance/session",
        params={"classroom_id": seed["room_id"], "period_id": seed["p1"], "session_date": seed["today"].isoformat()},
    ).json()
    assert [s["status"] for s in data["students"]] == ["present", "absent", "personal_leave"]
    assert data["session"]["topic"] == "สมการเชิงเส้น"
    assert data["session"]["can_edit"] is True


def test_second_save_updates_not_duplicates(seed):
    a = Api("teacher1")
    first = a.post("/api/attendance/sessions", json=session_body(seed)).json()
    second = a.post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "present", "present"))).json()
    assert second["id"] == first["id"] and second["created"] is False
    hist = a.get("/api/attendance/sessions").json()
    assert len(hist) == 1 and hist[0]["counts"] == {"present": 3}


def test_other_teacher_cannot_edit_but_admin_can(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed))
    r = Api("teacher2").post("/api/attendance/sessions", json=session_body(seed, statuses=("absent",) * 3))
    assert r.status_code == 403
    r = Api("admin").post("/api/attendance/sessions", json=session_body(seed, statuses=("absent",) * 3))
    assert r.status_code == 200


def test_future_date_rejected(seed):
    r = Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, day=seed["today"] + timedelta(days=1)))
    assert r.status_code == 400


def test_date_outside_term_rejected(seed):
    r = Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, day=seed["today"] - timedelta(days=90)))
    assert r.status_code == 400
    assert "เทอม" in r.json()["detail"]


def test_student_from_other_room_rejected(seed):
    body = session_body(seed)
    body["records"].append({"student_id": seed["outsider"], "status": "present"})
    assert Api("teacher1").post("/api/attendance/sessions", json=body).status_code == 400


def test_duplicate_student_in_body_rejected(seed):
    body = session_body(seed)
    body["records"].append(dict(body["records"][0]))
    assert Api("teacher1").post("/api/attendance/sessions", json=body).status_code == 422


def test_invalid_status_rejected(seed):
    assert Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "maybe", "late"))).status_code == 422


def test_history_only_own_for_teacher(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed))
    assert Api("teacher2").get("/api/attendance/sessions").json() == []
    assert len(Api("admin").get("/api/attendance/sessions", params={"mine": False}).json()) == 1


def test_admin_delete_session(seed):
    sid = Api("teacher1").post("/api/attendance/sessions", json=session_body(seed)).json()["id"]
    assert Api("teacher1").delete(f"/api/attendance/sessions/{sid}").status_code == 403
    assert Api("admin").delete(f"/api/attendance/sessions/{sid}").status_code == 204
    assert Api("admin").get("/api/attendance/sessions", params={"mine": False}).json() == []


def test_only_present_leave_absent_allowed(seed):
    a = Api("teacher1")
    for old in ("late", "sick_leave"):
        r = a.post("/api/attendance/sessions", json=session_body(seed, statuses=("present", old, "absent")))
        assert r.status_code == 422, old


def test_substitute_teacher(seed):
    t2 = Api("teacher2")
    teacher1_id = seed["t1"]
    opts = t2.get("/api/attendance/options").json()
    assert teacher1_id in [t["id"] for t in opts["teachers"]]
    r = t2.post("/api/attendance/sessions", json=session_body(seed, substitute_for_id=teacher1_id))
    assert r.status_code == 200, r.text
    data = t2.get("/api/attendance/session", params={"classroom_id": seed["room_id"], "period_id": seed["p1"], "session_date": seed["today"].isoformat()}).json()
    assert data["session"]["substitute_for_id"] == teacher1_id
    assert data["session"]["substitute_for_name"] == "ครูหนึ่ง"
    hist = t2.get("/api/attendance/sessions").json()
    assert hist[0]["substitute_for"] == "ครูหนึ่ง"
    rep = t2.get("/api/reports/term", params={"term_id": seed["term_id"], "classroom_id": seed["room_id"], "subject_id": seed["subject_id"]}).json()
    assert rep["sessions"][0]["substitute_for"] == "ครูหนึ่ง"
    # Unticking clears it; unknown teacher is refused.
    t2.post("/api/attendance/sessions", json=session_body(seed))
    assert t2.get("/api/attendance/sessions").json()[0]["substitute_for"] is None
    assert t2.post("/api/attendance/sessions", json=session_body(seed, substitute_for_id=99999)).status_code == 404

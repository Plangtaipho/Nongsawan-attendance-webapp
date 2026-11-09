import io

from openpyxl import load_workbook

from tests.conftest import Api, session_body


def test_audit_log_shows_edits_moves_deletes(seed):
    t1, admin = Api("teacher1"), Api("admin")
    sid = t1.post("/api/attendance/sessions", json=session_body(seed, period="p2")).json()["id"]
    admin.post("/api/attendance/sessions", json=session_body(seed, period="p2", statuses=("absent", "absent", "present")))
    admin.post(f"/api/attendance/sessions/{sid}/move", json={"period_id": seed["p1"], "session_date": seed["today"].isoformat()})
    t1.delete(f"/api/attendance/sessions/{sid}")

    rows = admin.get("/api/admin/audit").json()
    assert [r["action"] for r in rows] == ["delete", "move", "update"]  # first save hidden by default
    delete, move, update = rows
    assert delete["user"] == "ครูหนึ่ง" and "ม.1/1" in delete["what"] and "ผู้บันทึก ครูหนึ่ง" in delete["what"]
    assert "ม.1/1" in move["what"] and "ถูกลบภายหลัง" in move["what"]
    assert "คาบ 2" in move["change"] and "คาบ 1" in move["change"] and move["user"] == "แอดมิน"
    assert update["change"].startswith("เปลี่ยนสถานะ 2 คน") and "มา→ขาด" in update["change"]
    assert delete["at"].endswith("+00:00")

    assert len(admin.get("/api/admin/audit", params={"kind": "all"}).json()) == 4
    assert admin.get("/api/admin/audit", params={"kind": "student"}).json() == []
    assert t1.get("/api/admin/audit").status_code == 403


def test_backup_xlsx(seed):
    Api("teacher1").post("/api/attendance/sessions", json=session_body(seed, statuses=("present", "absent", "personal_leave")))
    r = Api("admin").get("/api/admin/backup.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["บันทึกการสอน", "การเข้าเรียน", "นักเรียน", "ครู", "รายวิชา", "ห้องเรียน", "ภาคเรียน", "คาบเรียน"]
    recs = list(wb["การเข้าเรียน"].values)
    assert len(recs) == 4 and [x[7] for x in recs[1:]] == ["มา", "ขาด", "ลา"]
    assert wb["บันทึกการสอน"]["G2"].value == "ครูหนึ่ง"
    header = [c.value for c in wb["ครู"][1]]
    assert not any("รหัสผ่าน" in (h or "") or "password" in (h or "").lower() for h in header)
    # Date range with no checks: header only.
    r = Api("admin").get("/api/admin/backup.xlsx", params={"date_from": "2000-01-01", "date_to": "2000-01-02"})
    assert len(list(load_workbook(io.BytesIO(r.content))["การเข้าเรียน"].values)) == 1
    assert Api("teacher1").get("/api/admin/backup.xlsx").status_code == 403

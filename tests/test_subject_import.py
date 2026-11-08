"""Import subjects from Excel: add new codes, update known ones, never guess the grade."""
from io import BytesIO

from openpyxl import Workbook

from tests.conftest import Api


def _xlsx(rows, header=("รหัสวิชา", "ชื่อวิชา", "กลุ่มสาระ", "ชั้น")) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _post(a, path, data):
    return a.post(path, files={"file": ("s.xlsx", data, "application/octet-stream")})


def test_import_adds_and_updates(seed):
    a = Api("admin")
    data = _xlsx([
        ("ค21101", "คณิตศาสตร์ 1 (ใหม่)", "", "ม.1"),       # existing code in seed: updated
        ("ศ0201", "ดนตรีศึกษา", "ศิลปะ", "ม.2"),
        ("ท21102", "ภาษาไทย 2", "", ""),                    # no grade given: every grade, not guessed
        ("กิจกรรม-ชุมนุม", "กิจกรรมชุมนุม", "กิจกรรมพัฒนาผู้เรียน", ""),
    ])
    p = _post(a, "/api/admin/subjects/import/preview", data).json()
    assert (p["total"], p["new_count"], p["update_count"], p["error_count"]) == (4, 3, 1, 0)
    assert _post(a, "/api/admin/subjects/import/commit", data).json() == {"created": 3, "updated": 1}
    subjects = {s["subject_code"]: s for s in a.get("/api/admin/subjects").json()}
    assert subjects["ค21101"]["name"] == "คณิตศาสตร์ 1 (ใหม่)"
    assert subjects["ท21102"]["grade_level"] is None and subjects["ท21102"]["learning_area"] == "ภาษาไทย"
    assert subjects["ศ0201"]["grade_level"] == "ม.2"
    assert subjects["กิจกรรม-ชุมนุม"]["learning_area"] == "กิจกรรมพัฒนาผู้เรียน"


def test_import_rejects_bad_rows(seed):
    a = Api("admin")
    data = _xlsx([("ค1", "ก", "", "ม.7"), ("ค1", "ข", "", ""), ("", "ไม่มีรหัส", "", ""), ("ค2", "x", "ดาราศาสตร์", "")])
    p = _post(a, "/api/admin/subjects/import/preview", data).json()
    assert p["error_count"] == 4
    assert _post(a, "/api/admin/subjects/import/commit", data).status_code == 400
    assert len(a.get("/api/admin/subjects").json()) == 1  # nothing saved


def test_import_needs_header_and_admin(seed):
    assert _post(Api("admin"), "/api/admin/subjects/import/preview", _xlsx([("a", "b")], header=("x", "y"))).status_code == 400
    assert _post(Api("teacher1"), "/api/admin/subjects/import/preview", _xlsx([])).status_code == 403
    assert Api("admin").get("/api/admin/subjects/import/template").status_code == 200

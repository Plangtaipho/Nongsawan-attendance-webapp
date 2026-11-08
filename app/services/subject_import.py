"""Import subjects (รายวิชา) from an Excel sheet: รหัสวิชา | ชื่อวิชา | กลุ่มสาระ | ชั้น.

Rows are matched by subject code: a new code is added, a known code is updated.
The grade is taken only from the file (empty = every grade); it is never guessed.
"""
from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GRADE_LEVELS, LEARNING_AREAS, Subject, guess_learning_area
from app.services.student_import import MAX_FILE_BYTES, ImportFileError, _cell_text, _norm

HEADERS = {
    "subject_code": {"รหัสวิชา", "รหัส", "subject_code", "code"},
    "name": {"ชื่อวิชา", "รายวิชา", "วิชา", "name"},
    "learning_area": {"กลุ่มสาระ", "กลุ่มสาระการเรียนรู้", "learning_area", "area"},
    "grade_level": {"ชั้น", "ระดับชั้น", "grade_level", "grade"},
}
TEMPLATE_HEADERS = ["รหัสวิชา", "ชื่อวิชา", "กลุ่มสาระ", "ชั้น"]


@dataclass
class SubjectRow:
    row_no: int
    sheet: str = ""
    subject_code: str = ""
    name: str = ""
    learning_area: str = ""
    grade_level: str = ""
    errors: list[str] = field(default_factory=list)
    action: str = ""


def _header(row: tuple) -> dict[str, int] | None:
    cols = {}
    for i, v in enumerate(row):
        t = _norm(_cell_text(v))
        for key, names in HEADERS.items():
            if t in names and key not in cols:
                cols[key] = i
    return cols if {"subject_code", "name"} <= cols.keys() else None


def _grade(text: str) -> str | None:
    t = text.replace(" ", "").replace("มัธยมศึกษาปีที่", "ม.")
    if t in ("", "ทุกชั้น", "-"):
        return ""
    if t.isdigit():
        t = "ม." + t
    return t if t in GRADE_LEVELS else None


def parse_xlsx(data: bytes) -> list[SubjectRow]:
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("ไฟล์ใหญ่เกิน 2 MB")
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ImportFileError("อ่านไฟล์ไม่ได้ กรุณาใช้ไฟล์ .xlsx") from exc

    rows: list[SubjectRow] = []
    seen: dict[str, str] = {}
    for ws in wb.worksheets:
        cols = None
        for n, raw in enumerate(ws.iter_rows(values_only=True), start=1):
            if cols is None:
                cols = _header(raw) if n <= 10 else None
                continue
            get = lambda k: _cell_text(raw[cols[k]]) if k in cols and cols[k] < len(raw) else ""  # noqa: E731
            r = SubjectRow(row_no=n, sheet=ws.title if len(wb.worksheets) > 1 else "",
                           subject_code=get("subject_code").replace(" ", ""), name=" ".join(get("name").split()),
                           learning_area=get("learning_area"), grade_level=get("grade_level"))
            if not (r.subject_code or r.name):
                continue
            if not r.subject_code:
                r.errors.append("ไม่มีรหัสวิชา")
            elif len(r.subject_code) > 20:
                r.errors.append("รหัสวิชายาวเกิน 20 ตัวอักษร")
            elif r.subject_code in seen:
                r.errors.append(f"รหัสวิชาซ้ำกับแถว {seen[r.subject_code]}")
            else:
                seen[r.subject_code] = f"{r.sheet + ' ' if r.sheet else ''}{n}"
            if not r.name:
                r.errors.append("ไม่มีชื่อวิชา")
            elif len(r.name) > 150:
                r.errors.append("ชื่อวิชายาวเกิน 150 ตัวอักษร")
            if r.learning_area and r.learning_area not in LEARNING_AREAS:
                r.errors.append(f"กลุ่มสาระ \"{r.learning_area}\" ไม่ถูกต้อง")
            elif not r.learning_area:
                r.learning_area = guess_learning_area(r.subject_code) or ""
            g = _grade(r.grade_level)
            if g is None:
                r.errors.append(f"ชั้น \"{r.grade_level}\" ไม่ถูกต้อง (ใช้ ม.1 ถึง ม.6 หรือเว้นว่าง = ทุกชั้น)")
            else:
                r.grade_level = g
            rows.append(r)
        if cols is None and ws.max_row and ws.max_row > 1 and len(wb.worksheets) == 1:
            raise ImportFileError("ไม่พบหัวตาราง ต้องมีคอลัมน์ รหัสวิชา และ ชื่อวิชา")
    if not rows:
        raise ImportFileError("ไม่พบรายวิชาในไฟล์ ต้องมีคอลัมน์ รหัสวิชา และ ชื่อวิชา")
    return rows


def preview(db: Session, rows: list[SubjectRow]) -> dict:
    existing = set(db.scalars(select(Subject.subject_code)).all())
    for r in rows:
        r.action = "update" if r.subject_code in existing else "new"
    ok = [r for r in rows if not r.errors]
    return {
        "total": len(rows),
        "error_count": len(rows) - len(ok),
        "new_count": sum(r.action == "new" for r in ok),
        "update_count": sum(r.action == "update" for r in ok),
        "rows": [r.__dict__ for r in rows],
    }


def commit(db: Session, rows: list[SubjectRow]) -> dict:
    if any(r.errors for r in rows):
        raise ImportFileError("ไฟล์ยังมีแถวที่ผิด กรุณาแก้ไขก่อนนำเข้า")
    by_code = {s.subject_code: s for s in db.scalars(select(Subject))}
    created = updated = 0
    for r in rows:
        s = by_code.get(r.subject_code)
        if s is None:
            db.add(Subject(subject_code=r.subject_code, name=r.name, learning_area=r.learning_area or None,
                           grade_level=r.grade_level or None, is_active=True))
            created += 1
        else:
            s.name, s.learning_area, s.grade_level, s.is_active = r.name, r.learning_area or None, r.grade_level or None, True
            updated += 1
    return {"created": created, "updated": updated}


def template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "รายวิชา"
    ws.append(TEMPLATE_HEADERS)
    ws.append(["ค21102", "คณิตศาสตร์ 2", "คณิตศาสตร์", "ม.1"])
    ws.append(["ศ0201", "ดนตรีศึกษา", "ศิลปะ", "ม.2"])
    ws.append(["กิจกรรม-ชุมนุม", "กิจกรรมชุมนุม", "กิจกรรมพัฒนาผู้เรียน", ""])
    for col, width in zip("ABCD", (16, 40, 30, 10)):
        ws.column_dimensions[col].width = width
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()

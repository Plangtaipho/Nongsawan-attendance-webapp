"""Read a student list from .xlsx, validate every row, and (on commit) save it.

Expected columns (Thai or English header, any order, on the first sheet):
    เลขประจำตัว | คำนำหน้า | ชื่อ | นามสกุล | ชั้น | ห้อง | เลขที่
    student_code | prefix | first_name | last_name | grade_level | room_no | class_number
"""
from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Classroom, Enrollment, Student, StudentStatus

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 3000

HEADER_ALIASES = {
    "student_code": {"เลขประจำตัว", "เลขประจำตัวนักเรียน", "รหัสนักเรียน", "student_code", "student id", "id"},
    "prefix": {"คำนำหน้า", "คำนำหน้าชื่อ", "prefix", "title"},
    "first_name": {"ชื่อ", "first_name", "first name", "firstname"},
    "last_name": {"นามสกุล", "last_name", "last name", "lastname", "surname"},
    "grade_level": {"ชั้น", "ระดับชั้น", "grade_level", "grade"},
    "room_no": {"ห้อง", "room_no", "room"},
    "class_number": {"เลขที่", "class_number", "no", "number"},
}
REQUIRED = ["student_code", "prefix", "first_name", "last_name", "grade_level", "room_no"]
TEMPLATE_HEADERS = ["เลขประจำตัว", "คำนำหน้า", "ชื่อ", "นามสกุล", "ชั้น", "ห้อง", "เลขที่"]


class ImportFileError(ValueError):
    """The file as a whole cannot be read (wrong type, no header, too big)."""


@dataclass
class ImportRow:
    row_no: int  # row number as shown in Excel
    student_code: str = ""
    prefix: str = ""
    first_name: str = ""
    last_name: str = ""
    grade_level: str = ""
    room_no: str = ""
    class_number: int | None = None
    errors: list[str] = field(default_factory=list)
    action: str = ""  # "new" or "update", filled by preview


def _cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # Excel stores 12345 as 12345.0
    return str(v).strip()


def _match_header(text: str) -> str | None:
    t = text.strip().lower()
    for key, names in HEADER_ALIASES.items():
        if t in {n.lower() for n in names}:
            return key
    return None


def parse_xlsx(data: bytes) -> list[ImportRow]:
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("ไฟล์ใหญ่เกิน 2 MB")
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several types for bad files
        raise ImportFileError("อ่านไฟล์ไม่ได้ กรุณาใช้ไฟล์ .xlsx") from exc
    ws = wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)

    # Find the header row within the first 10 rows (some files have a title row first).
    columns: dict[str, int] = {}
    header_row_no = 0
    for i, row in enumerate(rows_iter, start=1):
        found = {}
        for idx, v in enumerate(row):
            key = _match_header(_cell_text(v))
            if key and key not in found:
                found[key] = idx
        if all(k in found for k in REQUIRED):
            columns, header_row_no = found, i
            break
        if i >= 10:
            break
    if not columns:
        raise ImportFileError("ไม่พบหัวตาราง ต้องมีคอลัมน์: " + ", ".join(TEMPLATE_HEADERS[:6]))

    result: list[ImportRow] = []
    seen_codes: dict[str, int] = {}
    for row_no, row in enumerate(rows_iter, start=header_row_no + 1):
        def get(key):
            idx = columns.get(key)
            return _cell_text(row[idx]) if idx is not None and idx < len(row) else ""

        values = {k: get(k) for k in HEADER_ALIASES}
        if not any(values.values()):
            continue  # blank line
        if len(result) >= MAX_ROWS:
            raise ImportFileError(f"ไฟล์มีมากกว่า {MAX_ROWS} แถว")
        r = ImportRow(row_no=row_no)
        for k in REQUIRED:
            setattr(r, k, values[k])
            if not values[k]:
                r.errors.append(f"ไม่มี{dict(zip(REQUIRED, TEMPLATE_HEADERS))[k]}")
        limits = {"student_code": 20, "prefix": 20, "first_name": 100, "last_name": 100, "grade_level": 20, "room_no": 10}
        for k, n in limits.items():
            if len(getattr(r, k)) > n:
                r.errors.append(f"{k} ยาวเกิน {n} ตัวอักษร")
        if values["class_number"]:
            try:
                r.class_number = int(values["class_number"])
                if not 1 <= r.class_number <= 999:
                    raise ValueError
            except ValueError:
                r.errors.append("เลขที่ต้องเป็นตัวเลข 1-999")
        if r.student_code:
            if r.student_code in seen_codes:
                r.errors.append(f"เลขประจำตัวซ้ำกับแถว {seen_codes[r.student_code]}")
            else:
                seen_codes[r.student_code] = row_no
        result.append(r)
    if not result:
        raise ImportFileError("ไม่พบข้อมูลนักเรียนในไฟล์")
    return result


def preview(db: Session, rows: list[ImportRow], academic_year: int) -> dict:
    codes = [r.student_code for r in rows if r.student_code]
    existing = set(db.scalars(select(Student.student_code).where(Student.student_code.in_(codes))).all()) if codes else set()
    rooms = {(c.grade_level, c.room_no) for c in db.scalars(select(Classroom).where(Classroom.academic_year == academic_year))}
    new_rooms = sorted({(r.grade_level, r.room_no) for r in rows if r.grade_level and r.room_no} - rooms)
    for r in rows:
        r.action = "update" if r.student_code in existing else "new"
    return {
        "academic_year": academic_year,
        "total": len(rows),
        "error_count": sum(1 for r in rows if r.errors),
        "new_count": sum(1 for r in rows if not r.errors and r.action == "new"),
        "update_count": sum(1 for r in rows if not r.errors and r.action == "update"),
        "new_classrooms": [f"{g}/{n}" for g, n in new_rooms],
        "rows": [r.__dict__ for r in rows],
    }


def commit(db: Session, rows: list[ImportRow], academic_year: int) -> dict:
    """Save all rows in one transaction. Refuses if any row has an error."""
    if any(r.errors for r in rows):
        raise ImportFileError("ไฟล์ยังมีแถวที่ผิด กรุณาแก้ไขก่อนนำเข้า")

    rooms = {(c.grade_level, c.room_no): c for c in db.scalars(select(Classroom).where(Classroom.academic_year == academic_year))}
    created_rooms = 0
    for key in {(r.grade_level, r.room_no) for r in rows}:
        if key not in rooms:
            c = Classroom(academic_year=academic_year, grade_level=key[0], room_no=key[1])
            db.add(c)
            rooms[key] = c
            created_rooms += 1
    db.flush()

    codes = [r.student_code for r in rows]
    students = {s.student_code: s for s in db.scalars(select(Student).where(Student.student_code.in_(codes)))}
    year_room_ids = [c.id for c in rooms.values()]
    enrollments = {
        e.student_id: e
        for e in db.scalars(select(Enrollment).where(Enrollment.classroom_id.in_(year_room_ids)))
    }

    created = updated = 0
    for r in rows:
        s = students.get(r.student_code)
        if s is None:
            s = Student(student_code=r.student_code, prefix=r.prefix, first_name=r.first_name, last_name=r.last_name)
            db.add(s)
            db.flush()
            created += 1
        else:
            s.prefix, s.first_name, s.last_name = r.prefix, r.first_name, r.last_name
            s.status = StudentStatus.active
            updated += 1
        room = rooms[(r.grade_level, r.room_no)]
        e = enrollments.get(s.id)
        if e is None:
            db.add(Enrollment(student_id=s.id, classroom_id=room.id, class_number=r.class_number))
        else:
            # One classroom per student per academic year: move them if the file says so.
            e.classroom_id, e.class_number, e.is_active = room.id, r.class_number, True
    return {"created": created, "updated": updated, "created_classrooms": created_rooms}


def template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "รายชื่อนักเรียน"
    ws.append(TEMPLATE_HEADERS)
    ws.append(["10001", "ด.ช.", "ตัวอย่าง", "ใจดี", "ม.1", "1", 1])
    ws.append(["10002", "ด.ญ.", "ตัวอย่าง", "รักเรียน", "ม.1", "1", 2])
    for col, width in zip("ABCDEFG", [14, 10, 18, 18, 8, 8, 8]):
        ws.column_dimensions[col].width = width
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()

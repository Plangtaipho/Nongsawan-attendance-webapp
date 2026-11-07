"""Read a student list from .xlsx, validate every row, and (on commit) save it.

Template columns (Thai or English header, any order); see parse_xlsx for the class-list layout:
    เลขประจำตัว | คำนำหน้า | ชื่อ | นามสกุล | ชั้น | ห้อง | เลขที่
    student_code | prefix | first_name | last_name | grade_level | room_no | class_number
"""
from collections import Counter
from dataclasses import dataclass, field
import re
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
    "class_number": {"เลขที่", "ที่", "ลำดับ", "ลำดับที่", "class_number", "no", "number"},
    "full_name": {"ชื่อ-สกุล", "ชื่อ - สกุล", "ชื่อ สกุล", "ชื่อ-นามสกุล", "ชื่อ - นามสกุล", "ชื่อนามสกุล", "full_name", "full name", "name"},
}
REQUIRED = ["student_code", "prefix", "first_name", "last_name", "grade_level", "room_no"]
TEMPLATE_HEADERS = ["เลขประจำตัว", "คำนำหน้า", "ชื่อ", "นามสกุล", "ชั้น", "ห้อง", "เลขที่"]


class ImportFileError(ValueError):
    """The file as a whole cannot be read (wrong type, no header, too big)."""


@dataclass
class ImportRow:
    row_no: int  # row number as shown in Excel
    sheet: str = ""  # sheet name when the file has several sheets
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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).replace(" - ", "-").replace(" -", "-").replace("- ", "-")


def _match_header(text: str) -> str | None:
    t = _norm(text)
    if not t:
        return None
    for key, names in HEADER_ALIASES.items():
        if t in {_norm(n) for n in names}:
            return key
    return None


# Prefixes written in front of the name with no space, as in most Thai school lists. Longest first.
NAME_PREFIXES = ["เด็กชาย", "เด็กหญิง", "นางสาว", "ด.ช.", "ด.ญ.", "น.ส.", "นาย", "นาง"]
# "รายชื่อนักเรียนชั้นมัธยมศึกษาปีที่ 1/1" or "ชั้น ม.1/1" or "ป.3/2"
ROOM_IN_TITLE = re.compile(r"(มัธยมศึกษาปีที่|ประถมศึกษาปีที่|ม\.|ป\.)\s*(\d{1,2})\s*/\s*(\d{1,2})")


def split_full_name(full: str) -> tuple[str, str, str]:
    """'เด็กชายสมมติ  ทดลองดี' -> ('เด็กชาย', 'สมมติ', 'ทดลองดี'). Missing parts come back empty."""
    full = re.sub(r"\s+", " ", full).strip()
    prefix = next((p for p in NAME_PREFIXES if full.startswith(p)), "")
    rest = full[len(prefix):].strip().split(" ")
    first = rest[0] if rest and rest[0] else ""
    return prefix, first, " ".join(rest[1:])


def _room_from_title(texts: list[str]) -> tuple[str, str] | None:
    for t in texts:
        m = ROOM_IN_TITLE.search(t)
        if m:
            level = "ป." if m.group(1).startswith("ป") else "ม."
            return f"{level}{int(m.group(2))}", str(int(m.group(3)))
    return None


def _find_header(rows: list[tuple]) -> tuple[int, dict[str, int]] | None:
    """Index of the header row and its columns, looking at the first 15 rows."""
    for i, row in enumerate(rows[:15]):
        found: dict[str, int] = {}
        for idx, v in enumerate(row):
            key = _match_header(_cell_text(v))
            if key and key not in found:
                found[key] = idx
        has_name = {"first_name", "last_name"} <= found.keys() or "full_name" in found
        if "student_code" in found and has_name:
            return i, found
    return None


def parse_xlsx(data: bytes) -> list[ImportRow]:
    """Read every sheet. Two layouts are accepted, and can be mixed across sheets:
    1. The template: one row per student with prefix, first name, last name, grade and room columns.
    2. A class list per sheet, as schools usually keep it: a title such as
       "รายชื่อนักเรียนชั้นมัธยมศึกษาปีที่ 1/1", then columns ที่ | เลขประจำตัว | ชื่อ - สกุล.
    Sheets with no recognisable header (cover pages, summaries) are skipped.
    """
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("ไฟล์ใหญ่เกิน 2 MB")
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several types for bad files
        raise ImportFileError("อ่านไฟล์ไม่ได้ กรุณาใช้ไฟล์ .xlsx") from exc

    result: list[ImportRow] = []
    seen_codes: dict[str, str] = {}
    many_sheets = len(wb.worksheets) > 1
    no_room_sheets: list[str] = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True, max_row=MAX_ROWS + 50))
        header = _find_header(rows)
        if header is None:
            continue
        header_idx, columns = header
        sheet_room = None
        if not {"grade_level", "room_no"} <= columns.keys():
            titles = [_cell_text(v) for row in rows[:header_idx] for v in row] + [ws.title]
            sheet_room = _room_from_title(titles)
            if sheet_room is None:
                no_room_sheets.append(ws.title.strip())
                continue
        sheet = ws.title.strip() if many_sheets else ""

        for offset, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            def get(key, row=row):
                idx = columns.get(key)
                return _cell_text(row[idx]) if idx is not None and idx < len(row) else ""

            values = {k: get(k) for k in HEADER_ALIASES}
            if not values["student_code"] and not values["full_name"] and not values["first_name"]:
                continue  # blank line or footer text
            if len(result) >= MAX_ROWS:
                raise ImportFileError(f"ไฟล์มีมากกว่า {MAX_ROWS} แถว")
            if values["full_name"] and not values["first_name"]:
                p, f, l = split_full_name(values["full_name"])
                values["prefix"] = values["prefix"] or p
                values["first_name"], values["last_name"] = f, l
            if sheet_room:
                values["grade_level"], values["room_no"] = sheet_room
            r = ImportRow(row_no=offset, sheet=sheet)
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
            where = f"ชีต \"{sheet}\" แถว {offset}" if sheet else f"แถว {offset}"
            if r.student_code:
                if r.student_code in seen_codes:
                    r.errors.append(f"เลขประจำตัวซ้ำกับ {seen_codes[r.student_code]}")
                else:
                    seen_codes[r.student_code] = where
            result.append(r)
    if not result:
        if no_room_sheets:
            raise ImportFileError("ไม่พบชั้น/ห้องในชีต: " + ", ".join(no_room_sheets)
                                  + " (ต้องมีคอลัมน์ ชั้น และ ห้อง หรือหัวกระดาษเช่น \"มัธยมศึกษาปีที่ 1/1\")")
        raise ImportFileError("ไม่พบหัวตาราง ต้องมีคอลัมน์ เลขประจำตัว และ ชื่อ-สกุล (หรือ คำนำหน้า, ชื่อ, นามสกุล)")
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
        "rooms": [{"name": f"{g}/{n}", "count": c} for (g, n), c in sorted(Counter((r.grade_level, r.room_no) for r in rows if r.grade_level and r.room_no).items())],
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

"""Term attendance reports as an Excel workbook: a summary sheet plus one sheet per room and subject."""
import io
import re
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
MARKS = {"present": "/", "leave": "ล", "absent": "ข"}
LOW = 80

THIN = Side(style="thin", color="888888")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="EDE9FE")
BOLD = Font(bold=True)
RED = Font(color="B91C1C", bold=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def thai_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {str(d.year + 543)[2:]}"


def sheet_title(report: dict, used: set[str]) -> str:
    base = re.sub(r"[\\/?*\[\]:]", "-", f"{report['classroom']['name']} {report['subject']['code']}")[:28]
    title, n = base, 2
    while title.lower() in used:
        title, n = f"{base[:26]}~{n}", n + 1
    used.add(title.lower())
    return title


def _cell(ws, row, col, value=None, *, bold=False, fill=None, center=False, border=True, font=None):
    c = ws.cell(row=row, column=col, value=value)
    if font is not None:
        c.font = font
    elif bold:
        c.font = BOLD
    if fill:
        c.fill = fill
    if center:
        c.alignment = CENTER
    if border:
        c.border = BOX
    return c


def _report_sheet(ws, r: dict, school: str) -> None:
    sessions, students = r["sessions"], r["students"]
    n = len(sessions)
    term = f"ภาคเรียนที่ {r['term']['term_no']} ปีการศึกษา {r['term']['academic_year']}"
    ws.cell(row=1, column=1, value=f"{school} · แบบบันทึกเวลาเรียน").font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=f"ชั้น {r['classroom']['name']} · วิชา {r['subject']['code']} {r['subject']['name']} · {term}")
    ws.cell(row=3, column=1, value=f"บันทึกแล้ว {n} คาบ · / = มา, ล = ลา, ข = ขาด · ร้อยละ = มา ÷ คาบที่บันทึก · ตัวแดง = ต่ำกว่าร้อยละ {LOW}")

    h1, h2 = 5, 6
    for col, label in ((1, "เลขที่"), (2, "เลขประจำตัว"), (3, "ชื่อ - สกุล")):
        _cell(ws, h1, col, label, bold=True, fill=HEAD_FILL, center=True)
        _cell(ws, h2, col, None, fill=HEAD_FILL)
        ws.merge_cells(start_row=h1, start_column=col, end_row=h2, end_column=col)
    for i, s in enumerate(sessions):
        _cell(ws, h1, 4 + i, thai_date(s["date"]), fill=HEAD_FILL, center=True)
        _cell(ws, h2, 4 + i, f"คาบ {s['period_no']}", fill=HEAD_FILL, center=True)
        ws.column_dimensions[get_column_letter(4 + i)].width = 7
    sum_col = 4 + n
    for j, label in enumerate(("มา", "ลา", "ขาด", "ร้อยละ")):
        _cell(ws, h1, sum_col + j, label, bold=True, fill=HEAD_FILL, center=True)
        _cell(ws, h2, sum_col + j, None, fill=HEAD_FILL)
        ws.merge_cells(start_row=h1, start_column=sum_col + j, end_row=h2, end_column=sum_col + j)
        ws.column_dimensions[get_column_letter(sum_col + j)].width = 8

    row = h2 + 1
    for st in students:
        _cell(ws, row, 1, st["number"], center=True)
        _cell(ws, row, 2, st["code"], center=True)
        _cell(ws, row, 3, st["name"])
        for i, v in enumerate(st["statuses"]):
            _cell(ws, row, 4 + i, MARKS.get(v, "") if v else "", center=True, font=RED if v == "absent" else None)
        for j, k in enumerate(("present", "leave", "absent")):
            _cell(ws, row, sum_col + j, st["counts"][k], center=True)
        pct = st["percent"]
        c = _cell(ws, row, sum_col + 3, pct, center=True, font=RED if pct is not None and pct < LOW else None)
        c.number_format = "0.0"
        row += 1
    if not students:
        ws.cell(row=row, column=1, value="ไม่มีนักเรียนในห้องนี้")
        row += 1

    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 30
    ws.freeze_panes = ws.cell(row=h2 + 1, column=4)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{h1}:{h2}"


def _topics_sheet(ws, reports: list[dict]) -> None:
    heads = ("ห้อง", "รหัสวิชา", "วิชา", "วันที่", "คาบ", "หัวข้อที่สอน", "กิจกรรม / หมายเหตุ", "ผู้สอน")
    for col, label in enumerate(heads, start=1):
        _cell(ws, 1, col, label, bold=True, fill=HEAD_FILL, center=True)
    row = 1
    for r in reports:
        for s in r["sessions"]:
            row += 1
            teacher = s["teacher"] + (f" (สอนแทน {s['substitute_for']})" if s["substitute_for"] else "")
            values = (r["classroom"]["name"], r["subject"]["code"], r["subject"]["name"], thai_date(s["date"]),
                      s["period_no"], s["topic"] or "-", s["activity"] or "", teacher)
            for col, v in enumerate(values, start=1):
                _cell(ws, row, col, v, center=col in (1, 2, 4, 5))
    for col, w in zip("ABCDEFGH", (9, 11, 28, 11, 6, 40, 40, 26)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:H{max(row, 1)}"


def build(reports: list[dict], school: str, term_label: str) -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "สรุป"
    summary.cell(row=1, column=1, value=f"{school} · สรุปการเข้าเรียน {term_label}").font = Font(bold=True, size=14)
    heads = ("ห้อง", "รหัสวิชา", "ชื่อวิชา", "ผู้สอน", "คาบที่บันทึก", "นักเรียน", f"ต่ำกว่าร้อยละ {LOW}", "แผ่นงาน")
    for col, label in enumerate(heads, start=1):
        _cell(summary, 3, col, label, bold=True, fill=HEAD_FILL, center=True)
    used: set[str] = {"สรุป"}
    for i, r in enumerate(reports):
        title = sheet_title(r, used)
        _report_sheet(wb.create_sheet(title), r, school)
        teachers = sorted({s["teacher"] for s in r["sessions"]})
        low = sum(1 for st in r["students"] if st["percent"] is not None and st["percent"] < LOW)
        row = 4 + i
        values = (r["classroom"]["name"], r["subject"]["code"], r["subject"]["name"], ", ".join(teachers),
                  len(r["sessions"]), len(r["students"]), low, title)
        for col, v in enumerate(values, start=1):
            c = _cell(summary, row, col, v, center=col in (1, 2, 5, 6, 7), font=RED if col == 7 and low else None)
        c.hyperlink = f"#'{title}'!A1"
        c.font = Font(color="6D28D9", underline="single")
    _topics_sheet(wb.create_sheet("หัวข้อการสอน"), reports)
    if not reports:
        summary.cell(row=4, column=1, value="ยังไม่มีการบันทึกการสอนตามที่เลือก")
    for col, w in zip("ABCDEFGH", (9, 11, 32, 30, 12, 10, 16, 18)):
        summary.column_dimensions[col].width = w
    summary.freeze_panes = "A4"
    for ws in (summary, wb["หัวข้อการสอน"]):
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

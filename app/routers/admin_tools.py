"""Admin tools: the change log (audit log) and a full data backup as Excel."""
import io
import urllib.parse
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Response
from openpyxl import Workbook
from sqlalchemy import and_, not_, select
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.deps import require_admin, today, verify_csrf
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    AuditLog,
    Classroom,
    Enrollment,
    Period,
    Student,
    Subject,
    Term,
    User,
)
from app.services.reports import bucket

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin), Depends(verify_csrf)])

ACTIONS = {"create": "สร้าง", "update": "แก้ไข", "move": "ย้ายคาบ", "delete": "ลบ", "import": "นำเข้า"}
ENTITIES = {
    "attendance_session": "บันทึกการสอน", "student": "นักเรียน", "user": "บัญชีครู", "term": "ภาคเรียน",
    "classroom": "ห้องเรียน", "subject": "รายวิชา", "period": "คาบเรียน",
}
STATUS_TH = {"present": "มา", "leave": "ลา", "absent": "ขาด"}
TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _th(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {TH_MONTHS[d.month - 1]} {str(d.year + 543)[2:]}"


class _Names:
    """Small per-request caches so describing 100 log rows does not cost 100s of queries."""

    def __init__(self, db: Session):
        self.db = db
        self.c: dict[tuple, str] = {}

    def get(self, model, obj_id, fmt) -> str:
        if obj_id is None:
            return "-"
        key = (model.__name__, int(obj_id))
        if key not in self.c:
            obj = self.db.get(model, int(obj_id))
            self.c[key] = fmt(obj) if obj else f"#{obj_id}"
        return self.c[key]

    def room(self, i):
        return self.get(Classroom, i, lambda o: o.name)

    def subject(self, i):
        return self.get(Subject, i, lambda o: f"{o.subject_code} {o.name}")

    def period(self, i):
        return self.get(Period, i, lambda o: f"คาบ {o.period_no}")

    def user(self, i):
        return self.get(User, i, lambda o: o.full_name)


def _describe(db: Session, names: _Names, row: AuditLog) -> tuple[str, str]:
    """(what it was about, what changed) in Thai."""
    d = row.detail or {}
    if row.entity == "attendance_session":
        s = db.get(AttendanceSession, row.entity_id) if row.entity_id else None
        if s is not None and row.action != "delete":
            what = f"{names.room(s.classroom_id)} {names.period(s.period_id)} {_th(s.session_date.isoformat())} · {names.subject(s.subject_id)} (ผู้บันทึก {names.user(s.teacher_id)})"
        else:
            # The session is gone: borrow the details saved when it was deleted.
            gone = d if "classroom_id" in d else (db.scalar(
                select(AuditLog.detail).where(AuditLog.entity == "attendance_session", AuditLog.entity_id == row.entity_id, AuditLog.action == "delete")
            ) or {})
            what = None
            if "classroom_id" in gone:
                what = f"{names.room(gone.get('classroom_id'))} {names.period(gone.get('period_id'))} {_th(gone.get('date'))} · {names.subject(gone.get('subject_id'))} (ผู้บันทึก {names.user(gone.get('teacher_id'))})"
                if row.action != "delete":
                    what += " · รายการนี้ถูกลบภายหลัง"
        if what is None:
            what = f"บันทึก #{row.entity_id} (ถูกลบไปแล้ว)"
        if row.action == "move":
            f, t = d.get("from", {}), d.get("to", {})
            return what, f"จาก คาบ {f.get('period_no')} {_th(f.get('date'))} → คาบ {t.get('period_no')} {_th(t.get('date'))}"
        if row.action == "update":
            changed = d.get("changed") or {}
            if not changed:
                return what, "แก้หัวข้อ/วิชา/หมายเหตุ (สถานะนักเรียนไม่เปลี่ยน)"
            parts = []
            for sid, ch in list(changed.items())[:5]:
                name = names.get(Student, sid, lambda o: o.full_name)
                parts.append(f"{name}: {STATUS_TH.get(bucket(ch['from']), ch['from'])}→{STATUS_TH.get(bucket(ch['to']), ch['to'])}")
            more = f" และอีก {len(changed) - 5} คน" if len(changed) > 5 else ""
            return what, f"เปลี่ยนสถานะ {len(changed)} คน: " + ", ".join(parts) + more
        if row.action == "delete":
            recs = d.get("records") or {}
            return what, f"ลบทั้งรายการ (นักเรียน {len(recs)} คน หัวข้อ: {d.get('topic') or '-'})"
        return what, ""
    if row.entity == "student":
        who = names.get(Student, row.entity_id, lambda o: f"{o.student_code} {o.full_name}") if row.entity_id else ""
        if row.action == "import":
            return f"ไฟล์ {d.get('file') or ''}", ", ".join(f"{k}: {v}" for k, v in d.items() if k not in ("file",) and not isinstance(v, (list, dict)))
        if row.action == "delete":
            return f"{d.get('student_code', '')} {d.get('name', '')}".strip(), ""
        if row.action == "update":
            return who, "แก้ " + ", ".join(d.get("fields") or [])
        return who, f"ห้อง {d.get('classroom', '')}"
    if row.entity == "user":
        who = names.user(row.entity_id)
        if row.action == "update":
            return who, "แก้ " + ", ".join(d.get("fields") or [])
        return who, ""
    if row.entity == "subject" and row.action == "import":
        return "รายวิชาจากไฟล์ Excel", ", ".join(f"{k}: {v}" for k, v in d.items() if not isinstance(v, (list, dict)))
    if row.action == "delete":
        return d.get("name") or f"#{row.entity_id}", ""
    return f"#{row.entity_id}" if row.entity_id else "", ""


@router.get("/audit")
def audit_log(
    kind: str = "changes",
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """kind: changes (everything except new attendance saves), all, or an entity name."""
    stmt = select(AuditLog)
    if kind == "changes":
        stmt = stmt.where(not_(and_(AuditLog.entity == "attendance_session", AuditLog.action == "create")))
    elif kind != "all":
        stmt = stmt.where(AuditLog.entity == kind)
    # Days are Thai days; created_at is stored in UTC.
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, time()) - timedelta(hours=7))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), time()) - timedelta(hours=7))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
    names = _Names(db)
    out = []
    for r in rows:
        what, change = _describe(db, names, r)
        out.append({
            "id": r.id,
            "at": r.created_at.replace(tzinfo=UTC).isoformat(),
            "user": names.user(r.user_id),
            "action": r.action,
            "action_label": ACTIONS.get(r.action, r.action),
            "entity": r.entity,
            "entity_label": ENTITIES.get(r.entity, r.entity),
            "what": what,
            "change": change,
        })
    return out


# ---------------- Backup ----------------
def _sheet(wb: Workbook, title: str, header: list[str], rows) -> None:
    ws = wb.create_sheet(title)
    ws.append(header)
    for r in rows:
        ws.append(list(r))


@router.get("/backup.xlsx")
def backup(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
    """Everything needed to rebuild the records by hand: people, setup, every check and every student status.

    Accounts are listed without passwords. Attendance can be limited to a date range.
    """
    wb = Workbook(write_only=True)
    teacher, sub_for, editor = aliased(User), aliased(User), aliased(User)

    sess = (
        select(
            AttendanceSession.id, AttendanceSession.session_date, Period.period_no, Classroom.grade_level, Classroom.room_no,
            Subject.subject_code, Subject.name, teacher.full_name, sub_for.full_name, AttendanceSession.topic,
            AttendanceSession.activity, editor.full_name, AttendanceSession.edited_at, Term.term_no, Term.academic_year,
        )
        .join(Period, Period.id == AttendanceSession.period_id)
        .join(Classroom, Classroom.id == AttendanceSession.classroom_id)
        .join(Subject, Subject.id == AttendanceSession.subject_id)
        .join(Term, Term.id == AttendanceSession.term_id)
        .join(teacher, teacher.id == AttendanceSession.teacher_id)
        .outerjoin(sub_for, sub_for.id == AttendanceSession.substitute_for_id)
        .outerjoin(editor, editor.id == AttendanceSession.updated_by_id)
    )
    recs = (
        select(
            AttendanceRecord.session_id, AttendanceSession.session_date, Period.period_no, Classroom.grade_level, Classroom.room_no,
            Subject.subject_code, Student.student_code, Student.prefix, Student.first_name, Student.last_name,
            AttendanceRecord.status, AttendanceRecord.note,
        )
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(Period, Period.id == AttendanceSession.period_id)
        .join(Classroom, Classroom.id == AttendanceSession.classroom_id)
        .join(Subject, Subject.id == AttendanceSession.subject_id)
        .join(Student, Student.id == AttendanceRecord.student_id)
    )
    if date_from:
        sess, recs = sess.where(AttendanceSession.session_date >= date_from), recs.where(AttendanceSession.session_date >= date_from)
    if date_to:
        sess, recs = sess.where(AttendanceSession.session_date <= date_to), recs.where(AttendanceSession.session_date <= date_to)

    _sheet(wb, "บันทึกการสอน",
           ["รหัสบันทึก", "วันที่", "คาบ", "ห้อง", "รหัสวิชา", "ชื่อวิชา", "ผู้บันทึก", "สอนแทนครู", "หัวข้อ", "กิจกรรม/หมายเหตุ",
            "แก้ไขล่าสุดโดย", "แก้ไขล่าสุดเมื่อ (UTC)", "ภาคเรียน"],
           ((i, d, p, f"{g}/{r}", sc, sn, t, sf, tp, ac, ed, ea, f"{tn}/{ty}")
            for i, d, p, g, r, sc, sn, t, sf, tp, ac, ed, ea, tn, ty in db.execute(sess.order_by(AttendanceSession.session_date, Period.period_no, Classroom.grade_level, Classroom.room_no))))
    _sheet(wb, "การเข้าเรียน",
           ["รหัสบันทึก", "วันที่", "คาบ", "ห้อง", "รหัสวิชา", "เลขประจำตัว", "ชื่อ - สกุล", "สถานะ", "หมายเหตุ"],
           ((sid, d, p, f"{g}/{r}", sc, code, f"{pre}{fn} {ln}", STATUS_TH.get(bucket(st), st.value), note)
            for sid, d, p, g, r, sc, code, pre, fn, ln, st, note in db.execute(recs.order_by(AttendanceSession.session_date, Period.period_no, AttendanceRecord.session_id)).yield_per(2000)))

    room = aliased(Classroom)
    _sheet(wb, "นักเรียน", ["เลขประจำตัว", "คำนำหน้า", "ชื่อ", "นามสกุล", "สถานะ", "ปีการศึกษา", "ห้อง", "เลขที่", "อยู่ในห้องนี้"],
           ((s.student_code, s.prefix, s.first_name, s.last_name, s.status.value, c.academic_year if c else None,
             c.name if c else None, e.class_number if e else None, ("ใช่" if e.is_active else "ไม่") if e else None)
            for s, e, c in db.execute(
                select(Student, Enrollment, room).outerjoin(Enrollment, Enrollment.student_id == Student.id)
                .outerjoin(room, room.id == Enrollment.classroom_id).order_by(Student.student_code))))
    _sheet(wb, "ครู", ["ชื่อ - สกุล", "ชื่อผู้ใช้", "อีเมล", "สิทธิ์", "ใช้งาน"],
           ((u.full_name, u.username, u.email, u.role.value, u.is_active) for u in db.scalars(select(User).order_by(User.full_name))))
    _sheet(wb, "รายวิชา", ["รหัสวิชา", "ชื่อวิชา", "กลุ่มสาระ", "ชั้น", "ใช้งาน"],
           ((s.subject_code, s.name, s.learning_area, s.grade_level or "ทุกชั้น", s.is_active) for s in db.scalars(select(Subject).order_by(Subject.subject_code))))
    _sheet(wb, "ห้องเรียน", ["ปีการศึกษา", "ห้อง", "ใช้งาน"],
           ((c.academic_year, c.name, c.is_active) for c in db.scalars(select(Classroom).order_by(Classroom.academic_year, Classroom.grade_level, Classroom.room_no))))
    _sheet(wb, "ภาคเรียน", ["ปีการศึกษา", "ภาคเรียน", "เริ่ม", "สิ้นสุด", "ปัจจุบัน"],
           ((t.academic_year, t.term_no, t.start_date, t.end_date, t.is_current) for t in db.scalars(select(Term).order_by(Term.academic_year, Term.term_no))))
    _sheet(wb, "คาบเรียน", ["คาบ", "เริ่ม", "สิ้นสุด"],
           ((p.period_no, p.start_time.strftime("%H:%M"), p.end_time.strftime("%H:%M")) for p in db.scalars(select(Period).order_by(Period.period_no))))

    buf = io.BytesIO()
    wb.save(buf)
    stamp = today().isoformat()
    name = f"สำรองข้อมูล-บันทึกการสอน-{stamp}.xlsx"
    return Response(
        buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"backup_{stamp}.xlsx\"; filename*=UTF-8''{urllib.parse.quote(name)}"},
    )

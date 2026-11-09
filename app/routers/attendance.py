"""Taking attendance for one period, and listing past sessions."""
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, today, verify_csrf
from app.models import (
    LEARNING_AREAS,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    Classroom,
    Period,
    Role,
    Subject,
    User,
)
from app.schemas import SessionIn, SessionMoveIn
from app.services import audit
from app.services.school import classroom_students, current_academic_year, current_term, term_for_date

router = APIRouter(prefix="/api/attendance", tags=["attendance"], dependencies=[Depends(verify_csrf)])


def can_edit(user: User, s: AttendanceSession) -> bool:
    return user.role == Role.admin or s.teacher_id == user.id


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def utc_iso(dt: datetime | None) -> str | None:
    """Stored times are naive UTC; tell the browser so it shows Thai local time."""
    return dt.replace(tzinfo=UTC).isoformat() if dt else None


def edit_info(s: AttendanceSession) -> dict:
    return {
        "edited_by": s.updated_by.full_name if s.edited_at and s.updated_by else None,
        "edited_at": utc_iso(s.edited_at),
    }


def taken_message(s: AttendanceSession) -> str:
    return (
        f"คาบนี้ {s.teacher.full_name} บันทึกไว้แล้ว ({s.subject.name}) "
        "ถ้าบันทึกผิดคาบ ให้ผู้บันทึกหรือผู้ดูแลระบบเปิดคาบนั้นแล้วกด \"ย้ายไปคาบอื่น\" หรือ \"ลบบันทึกนี้\""
    )


def load_session(db: Session, session_id: int) -> AttendanceSession:
    s = db.scalar(
        select(AttendanceSession)
        .options(
            selectinload(AttendanceSession.records),
            selectinload(AttendanceSession.teacher),
            selectinload(AttendanceSession.subject),
            selectinload(AttendanceSession.period),
        )
        .where(AttendanceSession.id == session_id)
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการบันทึกการสอน")
    return s


@router.get("/options")
def options(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Everything the attendance form needs for its dropdowns."""
    year = current_academic_year(db)
    term = current_term(db)
    rooms = db.scalars(
        select(Classroom)
        .where(Classroom.academic_year == year, Classroom.is_active.is_(True))
        .order_by(Classroom.grade_level, Classroom.room_no)
    ).all()
    subjects = db.scalars(select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.subject_code)).all()
    periods = db.scalars(select(Period).order_by(Period.period_no)).all()
    return {
        "today": today().isoformat(),
        "academic_year": year,
        "term": {"id": term.id, "academic_year": term.academic_year, "term_no": term.term_no} if term else None,
        "classrooms": [{"id": c.id, "name": c.name, "grade": c.grade_level} for c in rooms],
        "learning_areas": [a for a in LEARNING_AREAS if any(s.learning_area == a for s in subjects)]
        + (["อื่นๆ"] if any(not s.learning_area for s in subjects) else []),
        "subjects": [
            {"id": s.id, "code": s.subject_code, "name": s.name, "area": s.learning_area or "อื่นๆ", "grade": s.grade_level}
            for s in subjects
        ],
        "teachers": [
            {"id": t.id, "name": t.full_name}
            for t in db.scalars(select(User).where(User.is_active.is_(True), User.id != user.id).order_by(User.full_name))
        ],
        "periods": [
            {"id": p.id, "no": p.period_no, "start": p.start_time.strftime("%H:%M"), "end": p.end_time.strftime("%H:%M")}
            for p in periods
        ],
    }


@router.get("/session")
def get_session(
    classroom_id: int,
    period_id: int,
    session_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Student list for a classroom, plus the saved check for that date and period if there is one."""
    room = db.get(Classroom, classroom_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบห้องเรียน")
    s = db.scalar(
        select(AttendanceSession)
        .options(
            selectinload(AttendanceSession.records),
            selectinload(AttendanceSession.teacher),
            selectinload(AttendanceSession.substitute_for),
            selectinload(AttendanceSession.subject),
            selectinload(AttendanceSession.updated_by),
        )
        .where(
            AttendanceSession.classroom_id == classroom_id,
            AttendanceSession.period_id == period_id,
            AttendanceSession.session_date == session_date,
        )
    )
    saved = {r.student_id: r for r in s.records} if s else {}
    students = [
        {
            "id": st.id,
            "code": st.student_code,
            "number": en.class_number,
            "name": st.full_name,
            "status": saved[st.id].status.value if st.id in saved else AttendanceStatus.present.value,
            "note": saved[st.id].note if st.id in saved else None,
        }
        for st, en in classroom_students(db, classroom_id)
    ]
    return {
        "classroom": {"id": room.id, "name": room.name},
        "students": students,
        "session": (
            {
                "id": s.id,
                "subject_id": s.subject_id,
                "subject_name": s.subject.name,
                "topic": s.topic,
                "activity": s.activity,
                "teacher_name": s.teacher.full_name,
                "substitute_for_id": s.substitute_for_id,
                "substitute_for_name": s.substitute_for.full_name if s.substitute_for else None,
                "updated_at": s.updated_at.isoformat(),
                **edit_info(s),
                "can_edit": can_edit(user, s),
            }
            if s
            else None
        ),
    }


@router.post("/sessions")
def save_session(body: SessionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Create the check for a classroom/date/period, or update it if it already exists."""
    if body.session_date > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่สามารถบันทึกการสอนล่วงหน้าได้")
    term = term_for_date(db, body.session_date)
    if term is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "วันที่นี้ไม่อยู่ในช่วงเทอมใด กรุณาให้ผู้ดูแลระบบตั้งค่าเทอม")
    if body.substitute_for_id is not None:
        absent = db.get(User, body.substitute_for_id)
        if absent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบครูที่สอนแทน")
    for model, obj_id, label in ((Classroom, body.classroom_id, "ห้องเรียน"), (Subject, body.subject_id, "วิชา"), (Period, body.period_id, "คาบเรียน")):
        if db.get(model, obj_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"ไม่พบ{label}")

    enrolled = {st.id for st, _ in classroom_students(db, body.classroom_id)}
    outsiders = {r.student_id for r in body.records} - enrolled
    if outsiders:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "มีนักเรียนที่ไม่ได้อยู่ในห้องนี้ กรุณารีเฟรชหน้าแล้วลองใหม่")

    s = db.scalar(
        select(AttendanceSession)
        .options(
            selectinload(AttendanceSession.records),
            selectinload(AttendanceSession.teacher),
            selectinload(AttendanceSession.subject),
        )
        .where(
            AttendanceSession.classroom_id == body.classroom_id,
            AttendanceSession.period_id == body.period_id,
            AttendanceSession.session_date == body.session_date,
        )
    )
    created = s is None
    if created:
        s = AttendanceSession(
            classroom_id=body.classroom_id,
            period_id=body.period_id,
            session_date=body.session_date,
            teacher_id=user.id,
        )
        db.add(s)
    elif not can_edit(user, s):
        raise HTTPException(status.HTTP_403_FORBIDDEN, taken_message(s))
    else:
        s.edited_at = utc_now()
    s.updated_by_id = user.id

    before = {r.student_id: r.status.value for r in s.records} if not created else {}
    s.term_id, s.subject_id = term.id, body.subject_id
    s.topic, s.activity = body.topic or None, body.activity or None
    # The recorder cannot be their own substitute.
    s.substitute_for_id = body.substitute_for_id if body.substitute_for_id != s.teacher_id else None

    existing = {r.student_id: r for r in s.records}
    for r in body.records:
        rec = existing.get(r.student_id)
        if rec is None:
            s.records.append(AttendanceRecord(student_id=r.student_id, status=r.status, note=r.note or None))
        else:
            rec.status, rec.note = r.status, r.note or None

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "มีผู้บันทึกคาบนี้พร้อมกัน กรุณาโหลดหน้าใหม่แล้วตรวจสอบอีกครั้ง")

    changed = {sid: {"from": before[sid], "to": r.status.value} for r in body.records if (sid := r.student_id) in before and before[sid] != r.status.value}
    audit.log(db, user, "create" if created else "update", "attendance_session", s.id, None if created else {"changed": changed})
    db.commit()

    counts: dict[str, int] = {}
    for r in body.records:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    return {"id": s.id, "created": created, "counts": counts}


@router.get("/sessions")
def list_sessions(
    mine: bool = True,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """History of checks. Teachers see their own; admins can see everyone's with mine=false."""
    stmt = select(AttendanceSession).options(
        selectinload(AttendanceSession.classroom),
        selectinload(AttendanceSession.subject),
        selectinload(AttendanceSession.period),
        selectinload(AttendanceSession.teacher),
        selectinload(AttendanceSession.substitute_for),
        selectinload(AttendanceSession.updated_by),
    )
    if mine or user.role != Role.admin:
        # Sessions I recorded, plus ones I last edited for someone else (e.g. an admin fixing a teacher's check).
        stmt = stmt.where(or_(AttendanceSession.teacher_id == user.id, AttendanceSession.updated_by_id == user.id))
    if date_from:
        stmt = stmt.where(AttendanceSession.session_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceSession.session_date <= date_to)
    sessions = db.scalars(
        stmt.order_by(AttendanceSession.session_date.desc(), AttendanceSession.period_id.desc()).limit(limit).offset(offset)
    ).all()

    ids = [s.id for s in sessions]
    counts: dict[int, dict[str, int]] = {i: {} for i in ids}
    if ids:
        for sid, st, n in db.execute(
            select(AttendanceRecord.session_id, AttendanceRecord.status, func.count())
            .where(AttendanceRecord.session_id.in_(ids))
            .group_by(AttendanceRecord.session_id, AttendanceRecord.status)
        ):
            counts[sid][st.value] = n
    return [
        {
            "id": s.id,
            "date": s.session_date.isoformat(),
            "classroom_id": s.classroom_id,
            "classroom": s.classroom.name,
            "period_id": s.period_id,
            "period_no": s.period.period_no,
            "subject": s.subject.name,
            "topic": s.topic,
            "teacher": s.teacher.full_name,
            "substitute_for": s.substitute_for.full_name if s.substitute_for else None,
            "is_mine": s.teacher_id == user.id,
            **edit_info(s),
            "counts": counts[s.id],
        }
        for s in sessions
    ]


@router.post("/sessions/{session_id}/move")
def move_session(session_id: int, body: SessionMoveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Move a check recorded in the wrong period or on the wrong date. Students, statuses and topic go with it."""
    s = load_session(db, session_id)
    if not can_edit(user, s):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ย้ายได้เฉพาะผู้บันทึกหรือผู้ดูแลระบบ")
    if body.session_date > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่สามารถย้ายไปวันที่ในอนาคตได้")
    term = term_for_date(db, body.session_date)
    if term is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "วันที่นี้ไม่อยู่ในช่วงเทอมใด")
    period = db.get(Period, body.period_id)
    if period is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบคาบเรียน")
    if (s.period_id, s.session_date) == (body.period_id, body.session_date):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "เป็นคาบและวันที่เดิมอยู่แล้ว")
    other = db.scalar(
        select(AttendanceSession)
        .options(selectinload(AttendanceSession.teacher), selectinload(AttendanceSession.subject))
        .where(
            AttendanceSession.classroom_id == s.classroom_id,
            AttendanceSession.period_id == body.period_id,
            AttendanceSession.session_date == body.session_date,
        )
    )
    if other is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"คาบ {period.period_no} วันนั้นมีบันทึกอยู่แล้วโดย {other.teacher.full_name} ({other.subject.name}) "
            "ถ้าเป็นบันทึกซ้ำ ให้ลบรายการที่ไม่ต้องการก่อน",
        )

    before = {"period_no": s.period.period_no, "period_id": s.period_id, "date": s.session_date.isoformat()}
    s.period_id, s.session_date, s.term_id = body.period_id, body.session_date, term.id
    s.updated_by_id, s.edited_at = user.id, utc_now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "มีผู้บันทึกคาบนั้นพร้อมกัน กรุณาโหลดหน้าใหม่แล้วตรวจสอบอีกครั้ง")
    audit.log(
        db, user, "move", "attendance_session", s.id,
        {"from": before, "to": {"period_no": period.period_no, "period_id": period.id, "date": body.session_date.isoformat()}},
    )
    db.commit()
    return {"id": s.id, "period_id": s.period_id, "period_no": period.period_no, "session_date": s.session_date.isoformat()}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The recorder or an admin can delete a check (e.g. recorded in the wrong room/period). Kept in the audit log."""
    s = load_session(db, session_id)
    if not can_edit(user, s):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ลบได้เฉพาะผู้บันทึกหรือผู้ดูแลระบบ")
    audit.log(
        db, user, "delete", "attendance_session", s.id,
        {
            "classroom_id": s.classroom_id, "subject_id": s.subject_id, "period_id": s.period_id,
            "date": s.session_date.isoformat(), "teacher_id": s.teacher_id, "topic": s.topic,
            "activity": s.activity, "substitute_for_id": s.substitute_for_id,
            "records": {r.student_id: {"status": r.status.value, "note": r.note} for r in s.records},
        },
    )
    db.delete(s)
    db.commit()

"""Queries behind the daily dashboard and the term report."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    Classroom,
    Enrollment,
    Period,
    Student,
    Subject,
    Term,
)

# Reports use the school's three statuses. Older values are folded in: late counts as มา,
# both kinds of leave count as ลา.
BUCKETS = ("present", "absent", "leave")
BUCKET_OF = {
    AttendanceStatus.present.value: "present",
    AttendanceStatus.late.value: "present",
    AttendanceStatus.absent.value: "absent",
    AttendanceStatus.personal_leave.value: "leave",
    AttendanceStatus.sick_leave.value: "leave",
}


def bucket(status: AttendanceStatus | str) -> str:
    return BUCKET_OF[status.value if isinstance(status, AttendanceStatus) else status]


def _empty_counts() -> dict[str, int]:
    return {b: 0 for b in BUCKETS}


def daily(db: Session, day: date, teacher_id: int | None, academic_year: int) -> dict:
    stmt = (
        select(AttendanceSession)
        .options(
            selectinload(AttendanceSession.records).selectinload(AttendanceRecord.student),
            selectinload(AttendanceSession.subject),
            selectinload(AttendanceSession.period),
            selectinload(AttendanceSession.teacher),
            selectinload(AttendanceSession.classroom),
        )
        .where(AttendanceSession.session_date == day)
    )
    if teacher_id:
        stmt = stmt.where(AttendanceSession.teacher_id == teacher_id)
    sessions = db.scalars(stmt).all()

    rooms = db.scalars(
        select(Classroom).where(Classroom.academic_year == academic_year, Classroom.is_active.is_(True)).order_by(Classroom.grade_level, Classroom.room_no)
    ).all()
    periods = db.scalars(select(Period).order_by(Period.period_no)).all()

    totals = _empty_counts()
    by_room: dict[int, dict] = {
        r.id: {"id": r.id, "name": r.name, "counts": _empty_counts(), "checked_periods": []} for r in rooms
    }
    not_present = []
    for s in sessions:
        room = by_room.setdefault(s.classroom_id, {"id": s.classroom_id, "name": s.classroom.name, "counts": _empty_counts(), "checked_periods": []})
        room["checked_periods"].append(s.period.period_no)
        for r in s.records:
            b = bucket(r.status)
            totals[b] += 1
            room["counts"][b] += 1
            if b != "present":
                not_present.append(
                    {
                        "classroom": s.classroom.name,
                        "period_no": s.period.period_no,
                        "subject": s.subject.name,
                        "student_code": r.student.student_code,
                        "name": r.student.full_name,
                        "status": b,
                        "note": r.note,
                    }
                )
    not_present.sort(key=lambda x: (x["classroom"], x["period_no"], x["student_code"]))
    total_records = sum(totals.values())
    return {
        "date": day.isoformat(),
        "session_count": len(sessions),
        "totals": totals,
        "attendance_rate": round(100 * totals["present"] / total_records, 1) if total_records else None,
        "periods": [p.period_no for p in periods],
        "classrooms": list(by_room.values()),
        "not_present": not_present,
    }


def term_report(db: Session, term: Term, classroom: Classroom, subject: Subject) -> dict:
    sessions = db.scalars(
        select(AttendanceSession)
        .options(
            selectinload(AttendanceSession.records),
            selectinload(AttendanceSession.period),
            selectinload(AttendanceSession.teacher),
            selectinload(AttendanceSession.substitute_for),
        )
        .where(
            AttendanceSession.term_id == term.id,
            AttendanceSession.classroom_id == classroom.id,
            AttendanceSession.subject_id == subject.id,
        )
        .order_by(AttendanceSession.session_date, AttendanceSession.period_id)
    ).all()

    # Students currently in the room, plus anyone with records here who has since moved.
    enrolled = db.execute(
        select(Student, Enrollment.class_number)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.classroom_id == classroom.id)
    ).all()
    students: dict[int, tuple[Student, int | None]] = {s.id: (s, n) for s, n in enrolled}
    recorded_ids = {r.student_id for s in sessions for r in s.records} - set(students)
    if recorded_ids:
        for s in db.scalars(select(Student).where(Student.id.in_(recorded_ids))):
            students[s.id] = (s, None)

    status_map = {(r.session_id, r.student_id): bucket(r.status) for s in sessions for r in s.records}
    rows = []
    for st, number in sorted(students.values(), key=lambda x: (x[1] is None, x[1] or 0, x[0].student_code)):
        statuses = [status_map.get((s.id, st.id)) for s in sessions]
        counts = _empty_counts()
        for v in statuses:
            if v:
                counts[v] += 1
        recorded = sum(counts.values())
        attended = counts["present"]
        rows.append(
            {
                "id": st.id,
                "code": st.student_code,
                "number": number,
                "name": st.full_name,
                "statuses": statuses,
                "counts": counts,
                "recorded": recorded,
                "percent": round(100 * attended / recorded, 1) if recorded else None,
            }
        )
    return {
        "term": {"id": term.id, "academic_year": term.academic_year, "term_no": term.term_no},
        "classroom": {"id": classroom.id, "name": classroom.name},
        "subject": {"id": subject.id, "code": subject.subject_code, "name": subject.name},
        "sessions": [
            {
                "id": s.id,
                "date": s.session_date.isoformat(),
                "period_no": s.period.period_no,
                "topic": s.topic,
                "activity": s.activity,
                "teacher": s.teacher.full_name,
                "substitute_for": s.substitute_for.full_name if s.substitute_for else None,
            }
            for s in sessions
        ],
        "students": rows,
    }

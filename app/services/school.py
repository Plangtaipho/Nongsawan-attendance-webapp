"""Small shared queries about the school's calendar and classrooms."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import today
from app.models import Classroom, Enrollment, Student, StudentStatus, Term


def current_term(db: Session) -> Term | None:
    return db.scalar(select(Term).where(Term.is_current.is_(True)))


def term_for_date(db: Session, d: date) -> Term | None:
    return db.scalar(select(Term).where(Term.start_date <= d, Term.end_date >= d).order_by(Term.start_date.desc()))


def current_academic_year(db: Session) -> int:
    t = current_term(db)
    if t:
        return t.academic_year
    latest = db.scalar(select(func.max(Classroom.academic_year)))
    if latest:
        return latest
    d = today()
    # Thai academic year starts in May; Jan-Apr still belongs to the previous year.
    return d.year + 543 - (1 if d.month < 5 else 0)


def classroom_students(db: Session, classroom_id: int) -> list[tuple[Student, Enrollment]]:
    """Active students enrolled in a classroom, ordered by class number then code."""
    rows = db.execute(
        select(Student, Enrollment)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(
            Enrollment.classroom_id == classroom_id,
            Enrollment.is_active.is_(True),
            Student.status == StudentStatus.active,
        )
        .order_by(Enrollment.class_number.is_(None), Enrollment.class_number, Student.student_code)
    ).all()
    return [(s, e) for s, e in rows]

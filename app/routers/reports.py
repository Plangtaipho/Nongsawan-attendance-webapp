"""Daily dashboard and term report (JSON). The printable page lives in pages.py."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, today
from app.models import Classroom, Role, Subject, Term, User
from app.services import reports
from app.services.school import current_academic_year

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/daily")
def daily(
    day: date | None = None,
    scope: str = "mine",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """scope=all shows the whole school (admin only); scope=mine shows the user's own checks."""
    if scope == "all" and user.role != Role.admin:
        scope = "mine"
    return reports.daily(db, day or today(), None if scope == "all" else user.id, current_academic_year(db))


def load_term_report(db: Session, term_id: int, classroom_id: int, subject_id: int) -> dict:
    term, room, subject = db.get(Term, term_id), db.get(Classroom, classroom_id), db.get(Subject, subject_id)
    if not (term and room and subject):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเทอม ห้อง หรือวิชาที่เลือก")
    return reports.term_report(db, term, room, subject)


@router.get("/term")
def term_report(
    term_id: int,
    classroom_id: int,
    subject_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return load_term_report(db, term_id, classroom_id, subject_id)


@router.get("/term-options")
def term_options(academic_year: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    terms = db.scalars(select(Term).order_by(Term.academic_year.desc(), Term.term_no.desc())).all()
    year = academic_year or current_academic_year(db)
    rooms = db.scalars(select(Classroom).where(Classroom.academic_year == year).order_by(Classroom.grade_level, Classroom.room_no)).all()
    subjects = db.scalars(select(Subject).order_by(Subject.subject_code)).all()
    return {
        "terms": [{"id": t.id, "label": f"{t.term_no}/{t.academic_year}", "academic_year": t.academic_year, "is_current": t.is_current} for t in terms],
        "academic_year": year,
        "classrooms": [{"id": c.id, "name": c.name} for c in rooms],
        "subjects": [{"id": s.id, "code": s.subject_code, "name": s.name} for s in subjects],
    }

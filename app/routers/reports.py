"""Daily dashboard and term report (JSON). The printable page lives in pages.py."""
from datetime import date

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, today
from app.models import Classroom, Role, Subject, Term, User
from app.config import get_settings
from app.services import report_xlsx, reports
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


def load_term_reports(db: Session, term_id: int, classroom_id: int | None, subject_id: int | None) -> tuple[Term, list[dict]]:
    """Reports for the chosen room/subject; None means every room or every subject with checks this term."""
    term = db.get(Term, term_id)
    if term is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบภาคเรียนที่เลือก")
    if classroom_id is not None and db.get(Classroom, classroom_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบห้องที่เลือก")
    if subject_id is not None and db.get(Subject, subject_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบวิชาที่เลือก")
    return term, reports.term_reports(db, term, classroom_id, subject_id)


@router.get("/term-list")
def term_report_list(
    term_id: int,
    classroom_id: int | None = None,
    subject_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One summary line per room and subject, for the "all rooms" / "all subjects" view."""
    _, items = load_term_reports(db, term_id, classroom_id, subject_id)
    return [
        {
            "classroom": r["classroom"],
            "subject": r["subject"],
            "teachers": sorted({s["teacher"] for s in r["sessions"]}),
            "sessions": len(r["sessions"]),
            "students": len(r["students"]),
            "low": sum(1 for st in r["students"] if st["percent"] is not None and st["percent"] < report_xlsx.LOW),
        }
        for r in items
    ]


@router.get("/term.xlsx")
def term_report_xlsx(
    term_id: int,
    classroom_id: int | None = None,
    subject_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    term, items = load_term_reports(db, term_id, classroom_id, subject_id)
    label = f"ภาคเรียนที่ {term.term_no}/{term.academic_year}"
    data = report_xlsx.build(items, get_settings().school_name, label)
    parts = [f"รายงานเวลาเรียน-{term.term_no}-{term.academic_year}"]
    if classroom_id is not None and items:
        parts.append(items[0]["classroom"]["name"].replace("/", "-"))
    elif classroom_id is None:
        parts.append("ทุกห้อง")
    if subject_id is not None and items:
        parts.append(items[0]["subject"]["code"])
    elif subject_id is None:
        parts.append("ทุกวิชา")
    name = "_".join(parts) + ".xlsx"
    ascii_name = f"term_report_{term.term_no}_{term.academic_year}.xlsx"
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"},
    )


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

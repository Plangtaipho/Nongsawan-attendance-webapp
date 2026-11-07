"""Admin back office: teachers, terms, classrooms, subjects, periods, students, Excel import."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.deps import require_admin, verify_csrf
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    Classroom,
    Enrollment,
    Period,
    Role,
    Student,
    Subject,
    Term,
    User,
)
from app.schemas import (
    ClassroomIn,
    ClassroomOut,
    PeriodIn,
    PeriodOut,
    StudentIn,
    StudentOut,
    StudentUpdate,
    SubjectIn,
    SubjectOut,
    TermIn,
    TermOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.security import hash_password
from app.services import audit, student_import
from app.services.school import current_academic_year

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin), Depends(verify_csrf)])


def _in_use(db: Session, column, value) -> bool:
    return bool(db.scalar(select(func.count()).where(column == value)))


def _delete(db: Session, admin: User, obj, entity: str) -> None:
    audit.log(db, admin, "delete", entity, obj.id)
    db.delete(obj)
    db.commit()


def _commit(db: Session, conflict_msg: str) -> None:
    """Commit, turning a unique-constraint clash into a clear 409 for the user."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_msg)


def _get(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ไม่พบ{label}")
    return obj


# ---------------- Users ----------------
@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.is_active.desc(), User.full_name)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = User(
        username=body.username,
        full_name=body.full_name,
        email=(body.email or "").strip().lower() or None,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(u)
    _commit(db, "ชื่อผู้ใช้หรืออีเมลนี้มีอยู่แล้ว")
    audit.log(db, admin, "create", "user", u.id, {"username": u.username, "role": u.role.value})
    db.commit()
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _get(db, User, user_id, "ผู้ใช้")
    if u.id == admin.id and (body.is_active is False or body.role == Role.teacher):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่สามารถปิดบัญชีหรือลดสิทธิ์ของตัวเองได้")
    changes = body.model_dump(exclude_unset=True)
    new_password = changes.pop("new_password", None)
    if "email" in changes:
        changes["email"] = (changes["email"] or "").strip().lower() or None
    for k, v in changes.items():
        setattr(u, k, v)
    if new_password:
        u.password_hash = hash_password(new_password)
    audit.log(db, admin, "update", "user", u.id, {"fields": sorted(changes) + (["password"] if new_password else [])})
    _commit(db, "อีเมลนี้มีผู้ใช้อื่นใช้อยู่แล้ว")
    return u


# ---------------- Terms ----------------
@router.get("/terms", response_model=list[TermOut])
def list_terms(db: Session = Depends(get_db)):
    return db.scalars(select(Term).order_by(Term.academic_year.desc(), Term.term_no.desc())).all()


def _save_term(db: Session, t: Term, body: TermIn) -> Term:
    overlap = db.scalar(
        select(Term).where(Term.id != (t.id or 0), Term.start_date <= body.end_date, Term.end_date >= body.start_date)
    )
    if overlap:
        raise HTTPException(status.HTTP_409_CONFLICT, f"ช่วงวันที่ทับกับเทอม {overlap.term_no}/{overlap.academic_year}")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    if body.is_current:
        db.execute(update(Term).where(Term.id != (t.id or 0)).values(is_current=False))
    db.add(t)
    _commit(db, "มีเทอมนี้ในปีการศึกษานี้แล้ว")
    return t


@router.post("/terms", response_model=TermOut, status_code=201)
def create_term(body: TermIn, db: Session = Depends(get_db)):
    return _save_term(db, Term(), body)


@router.put("/terms/{term_id}", response_model=TermOut)
def update_term(term_id: int, body: TermIn, db: Session = Depends(get_db)):
    return _save_term(db, _get(db, Term, term_id, "เทอม"), body)


@router.delete("/terms/{term_id}", status_code=204)
def delete_term(term_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    t = _get(db, Term, term_id, "เทอม")
    if _in_use(db, AttendanceSession.term_id, t.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "เทอมนี้มีการบันทึกการสอนแล้ว ลบไม่ได้")
    _delete(db, admin, t, "term")


# ---------------- Classrooms ----------------
@router.get("/classrooms", response_model=list[ClassroomOut])
def list_classrooms(academic_year: int | None = None, db: Session = Depends(get_db)):
    year = academic_year or current_academic_year(db)
    return db.scalars(
        select(Classroom).where(Classroom.academic_year == year).order_by(Classroom.grade_level, Classroom.room_no)
    ).all()


@router.post("/classrooms", response_model=ClassroomOut, status_code=201)
def create_classroom(body: ClassroomIn, db: Session = Depends(get_db)):
    c = Classroom(**body.model_dump())
    db.add(c)
    _commit(db, "มีห้องนี้ในปีการศึกษานี้แล้ว")
    return c


@router.put("/classrooms/{classroom_id}", response_model=ClassroomOut)
def update_classroom(classroom_id: int, body: ClassroomIn, db: Session = Depends(get_db)):
    c = _get(db, Classroom, classroom_id, "ห้องเรียน")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    _commit(db, "มีห้องนี้ในปีการศึกษานี้แล้ว")
    return c


@router.delete("/classrooms/{classroom_id}", status_code=204)
def delete_classroom(classroom_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = _get(db, Classroom, classroom_id, "ห้องเรียน")
    if _in_use(db, AttendanceSession.classroom_id, c.id) or _in_use(db, Enrollment.classroom_id, c.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "ห้องนี้มีนักเรียนหรือการบันทึกการสอนแล้ว ลบไม่ได้ (ปิดใช้งานแทนได้)")
    _delete(db, admin, c, "classroom")


# ---------------- Subjects ----------------
@router.get("/subjects", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    return db.scalars(select(Subject).order_by(Subject.is_active.desc(), Subject.subject_code)).all()


@router.post("/subjects", response_model=SubjectOut, status_code=201)
def create_subject(body: SubjectIn, db: Session = Depends(get_db)):
    s = Subject(**body.model_dump())
    db.add(s)
    _commit(db, "รหัสวิชานี้มีอยู่แล้ว")
    return s


@router.put("/subjects/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, body: SubjectIn, db: Session = Depends(get_db)):
    s = _get(db, Subject, subject_id, "วิชา")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    _commit(db, "รหัสวิชานี้มีอยู่แล้ว")
    return s


@router.delete("/subjects/{subject_id}", status_code=204)
def delete_subject(subject_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = _get(db, Subject, subject_id, "วิชา")
    if _in_use(db, AttendanceSession.subject_id, s.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "วิชานี้มีการบันทึกการสอนแล้ว ลบไม่ได้ (ปิดใช้งานแทนได้)")
    _delete(db, admin, s, "subject")


# ---------------- Periods ----------------
@router.get("/periods", response_model=list[PeriodOut])
def list_periods(db: Session = Depends(get_db)):
    return db.scalars(select(Period).order_by(Period.period_no)).all()


@router.post("/periods", response_model=PeriodOut, status_code=201)
def create_period(body: PeriodIn, db: Session = Depends(get_db)):
    p = Period(**body.model_dump())
    db.add(p)
    _commit(db, "มีคาบที่นี้อยู่แล้ว")
    return p


@router.put("/periods/{period_id}", response_model=PeriodOut)
def update_period(period_id: int, body: PeriodIn, db: Session = Depends(get_db)):
    p = _get(db, Period, period_id, "คาบเรียน")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    _commit(db, "มีคาบที่นี้อยู่แล้ว")
    return p


@router.delete("/periods/{period_id}", status_code=204)
def delete_period(period_id: int, db: Session = Depends(get_db)):
    p = _get(db, Period, period_id, "คาบเรียน")
    if db.scalar(select(func.count()).select_from(AttendanceSession).where(AttendanceSession.period_id == p.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "คาบนี้มีการบันทึกการสอนแล้ว ลบไม่ได้")
    db.delete(p)
    db.commit()


# ---------------- Students ----------------
def _student_out(s: Student, e: Enrollment | None, room: Classroom | None) -> StudentOut:
    return StudentOut(
        id=s.id,
        student_code=s.student_code,
        prefix=s.prefix,
        first_name=s.first_name,
        last_name=s.last_name,
        full_name=s.full_name,
        status=s.status,
        classroom_id=room.id if room else None,
        classroom_name=room.name if room else None,
        class_number=e.class_number if e else None,
    )


@router.get("/students", response_model=list[StudentOut])
def list_students(
    classroom_id: int | None = None,
    q: str | None = Query(default=None, max_length=100),
    academic_year: int | None = None,
    db: Session = Depends(get_db),
):
    year = academic_year or current_academic_year(db)
    # This year's enrollments as a derived table. TiDB rejects a subquery inside a JOIN ... ON,
    # so the year filter lives in the derived table instead of the ON clause.
    year_enroll = (
        select(Enrollment)
        .join(Classroom, Classroom.id == Enrollment.classroom_id)
        .where(Classroom.academic_year == year)
        .subquery()
    )
    Enrollment_ = aliased(Enrollment, year_enroll)
    stmt = (
        select(Student, Enrollment_, Classroom)
        .select_from(Student)
        .outerjoin(Enrollment_, Enrollment_.student_id == Student.id)
        .outerjoin(Classroom, Classroom.id == Enrollment_.classroom_id)
    )
    if classroom_id:
        stmt = stmt.where(Enrollment_.classroom_id == classroom_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Student.student_code.like(like), Student.first_name.like(like), Student.last_name.like(like)))
    if not classroom_id and not q:
        stmt = stmt.where(Enrollment_.id.is_not(None))  # default view: this year's enrolled students
    stmt = stmt.order_by(Classroom.grade_level, Classroom.room_no, Enrollment_.class_number, Student.student_code).limit(1000)
    return [_student_out(s, e, c) for s, e, c in db.execute(stmt).all()]


def _set_enrollment(db: Session, student_id: int, classroom: Classroom, class_number: int | None) -> None:
    """One classroom per student per academic year: update the existing row or add one."""
    year_rooms = select(Classroom.id).where(Classroom.academic_year == classroom.academic_year)
    e = db.scalar(select(Enrollment).where(Enrollment.student_id == student_id, Enrollment.classroom_id.in_(year_rooms)))
    if e is None:
        db.add(Enrollment(student_id=student_id, classroom_id=classroom.id, class_number=class_number))
    else:
        e.classroom_id, e.class_number, e.is_active = classroom.id, class_number, True


@router.post("/students", response_model=StudentOut, status_code=201)
def create_student(body: StudentIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    room = _get(db, Classroom, body.classroom_id, "ห้องเรียน")
    s = Student(student_code=body.student_code, prefix=body.prefix, first_name=body.first_name, last_name=body.last_name)
    db.add(s)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "เลขประจำตัวนี้มีอยู่แล้ว")
    _set_enrollment(db, s.id, room, body.class_number)
    audit.log(db, admin, "create", "student", s.id, {"student_code": s.student_code, "classroom": room.name})
    db.commit()
    e = db.scalar(select(Enrollment).where(Enrollment.student_id == s.id, Enrollment.classroom_id == room.id))
    return _student_out(s, e, room)


@router.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Only for a student added by mistake: one with attendance history must be set inactive instead."""
    s = _get(db, Student, student_id, "นักเรียน")
    if _in_use(db, AttendanceRecord.student_id, s.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "นักเรียนคนนี้มีประวัติการบันทึกการสอนแล้ว ลบไม่ได้ (เปลี่ยนสถานะแทนได้)")
    for e in db.scalars(select(Enrollment).where(Enrollment.student_id == s.id)):
        db.delete(e)
    audit.log(db, admin, "delete", "student", s.id, {"student_code": s.student_code})
    db.delete(s)
    db.commit()


@router.patch("/students/{student_id}", response_model=StudentOut)
def update_student(student_id: int, body: StudentUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = _get(db, Student, student_id, "นักเรียน")
    changes = body.model_dump(exclude_unset=True)
    classroom_id = changes.pop("classroom_id", None)
    class_number_set = "class_number" in changes
    class_number = changes.pop("class_number", None)
    for k, v in changes.items():
        if v is not None:
            setattr(s, k, v)
    room = None
    if classroom_id is not None:
        room = _get(db, Classroom, classroom_id, "ห้องเรียน")
        _set_enrollment(db, s.id, room, class_number)
    elif class_number_set:
        year_rooms = select(Classroom.id).where(Classroom.academic_year == current_academic_year(db))
        e = db.scalar(select(Enrollment).where(Enrollment.student_id == s.id, Enrollment.classroom_id.in_(year_rooms)))
        if e:
            e.class_number = class_number
    audit.log(db, admin, "update", "student", s.id, {"fields": sorted(body.model_dump(exclude_unset=True))})
    _commit(db, "เลขประจำตัวนี้มีอยู่แล้ว")

    year = room.academic_year if room else current_academic_year(db)
    year_rooms = select(Classroom.id).where(Classroom.academic_year == year)
    e = db.scalar(select(Enrollment).where(Enrollment.student_id == s.id, Enrollment.classroom_id.in_(year_rooms)))
    return _student_out(s, e, db.get(Classroom, e.classroom_id) if e else None)


# ---------------- Excel import ----------------
@router.get("/students/import/template")
def import_template():
    return Response(
        student_import.template_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="student_template.xlsx"'},
    )


async def _read_upload(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "รองรับเฉพาะไฟล์ .xlsx")
    data = await file.read(student_import.MAX_FILE_BYTES + 1)
    if len(data) > student_import.MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไฟล์ใหญ่เกิน 2 MB")
    return data


@router.post("/students/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    academic_year: int = Form(..., ge=2500, le=2700),
    db: Session = Depends(get_db),
):
    data = await _read_upload(file)
    try:
        rows = student_import.parse_xlsx(data)
    except student_import.ImportFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return student_import.preview(db, rows, academic_year)


@router.post("/students/import/commit")
async def import_commit(
    file: UploadFile = File(...),
    academic_year: int = Form(..., ge=2500, le=2700),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    data = await _read_upload(file)
    try:
        rows = student_import.parse_xlsx(data)
        result = student_import.commit(db, rows, academic_year)
    except student_import.ImportFileError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    audit.log(db, admin, "import", "student", None, {"academic_year": academic_year, **result, "file": file.filename})
    _commit(db, "ข้อมูลขัดแย้งกับข้อมูลในระบบ กรุณาลองใหม่")
    return result

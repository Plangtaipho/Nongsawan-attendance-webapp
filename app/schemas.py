"""Pydantic request/response schemas."""
from datetime import date, time
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import LEARNING_AREAS, AttendanceStatus, Role, StudentStatus, guess_learning_area
from app.security import MAX_PASSWORD_BYTES


def _check_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร")
    if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("รหัสผ่านยาวเกินไป")
    return v


Password = Annotated[str, AfterValidator(_check_password)]


class In(BaseModel):
    """Base for request bodies: trims spaces around every string."""
    model_config = ConfigDict(str_strip_whitespace=True)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginIn(In):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(In):
    current_password: str = Field(max_length=200)
    new_password: Password


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str | None
    role: Role
    is_active: bool


# ---------- Users (admin) ----------
class UserCreate(In):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
    full_name: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    role: Role = Role.teacher
    password: Password


class UserUpdate(In):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    new_password: str | None = None

    @field_validator("new_password")
    @classmethod
    def _np(cls, v):
        return None if v in (None, "") else _check_password(v)


# ---------- Terms ----------
class TermIn(In):
    academic_year: int = Field(ge=2500, le=2700)
    term_no: int = Field(ge=1, le=3)
    start_date: date
    end_date: date
    is_current: bool = False

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("วันสิ้นสุดเทอมต้องอยู่หลังวันเริ่มเทอม")
        return self


class TermOut(ORM):
    id: int
    academic_year: int
    term_no: int
    start_date: date
    end_date: date
    is_current: bool


# ---------- Classrooms ----------
class ClassroomIn(In):
    academic_year: int = Field(ge=2500, le=2700)
    grade_level: str = Field(min_length=1, max_length=20)
    room_no: str = Field(min_length=1, max_length=10)
    is_active: bool = True


class ClassroomOut(ORM):
    id: int
    academic_year: int
    grade_level: str
    room_no: str
    name: str
    is_active: bool


# ---------- Subjects ----------
class SubjectIn(In):
    subject_code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    learning_area: str | None = None  # empty: guessed from the subject code
    is_active: bool = True

    @model_validator(mode="after")
    def _area(self):
        if not self.learning_area:
            self.learning_area = guess_learning_area(self.subject_code)
        elif self.learning_area not in LEARNING_AREAS:
            raise ValueError("กลุ่มสาระไม่ถูกต้อง")
        return self


class SubjectOut(ORM):
    id: int
    subject_code: str
    name: str
    learning_area: str | None
    is_active: bool


# ---------- Periods ----------
class PeriodIn(In):
    period_no: int = Field(ge=1, le=20)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _times(self):
        if self.end_time <= self.start_time:
            raise ValueError("เวลาสิ้นสุดคาบต้องอยู่หลังเวลาเริ่ม")
        return self


class PeriodOut(ORM):
    id: int
    period_no: int
    start_time: time
    end_time: time


# ---------- Students ----------
class StudentIn(In):
    student_code: str = Field(min_length=1, max_length=20)
    prefix: str = Field(min_length=1, max_length=20)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    classroom_id: int
    class_number: int | None = Field(default=None, ge=1, le=999)


class StudentUpdate(In):
    student_code: str | None = Field(default=None, min_length=1, max_length=20)
    prefix: str | None = Field(default=None, min_length=1, max_length=20)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    status: StudentStatus | None = None
    classroom_id: int | None = None
    class_number: int | None = Field(default=None, ge=1, le=999)


class StudentOut(BaseModel):
    id: int
    student_code: str
    prefix: str
    first_name: str
    last_name: str
    full_name: str
    status: StudentStatus
    classroom_id: int | None = None
    classroom_name: str | None = None
    class_number: int | None = None


# ---------- Attendance ----------
ALLOWED_STATUSES = {AttendanceStatus.present, AttendanceStatus.absent, AttendanceStatus.personal_leave}


class RecordIn(In):
    student_id: int
    status: AttendanceStatus
    note: str | None = Field(default=None, max_length=255)

    @field_validator("status")
    @classmethod
    def _only_school_statuses(cls, v: AttendanceStatus) -> AttendanceStatus:
        if v not in ALLOWED_STATUSES:
            raise ValueError("สถานะต้องเป็น มา ลา หรือ ขาด")
        return v


class SessionIn(In):
    classroom_id: int
    subject_id: int
    period_id: int
    session_date: date
    topic: str | None = Field(default=None, max_length=500)
    activity: str | None = Field(default=None, max_length=5000)
    records: list[RecordIn] = Field(min_length=1, max_length=200)

    @field_validator("records")
    @classmethod
    def _unique_students(cls, v: list[RecordIn]):
        ids = [r.student_id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("มีรายชื่อนักเรียนซ้ำในการบันทึก")
        return v

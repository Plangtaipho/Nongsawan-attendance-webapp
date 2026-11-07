"""SQLAlchemy ORM models. Mirrors the approved schema in the project plan."""
import enum
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"


class StudentStatus(str, enum.Enum):
    active = "active"
    transferred = "transferred"
    graduated = "graduated"
    inactive = "inactive"


class AttendanceStatus(str, enum.Enum):
    # The school records only มา / ลา / ขาด. "ลา" is stored as personal_leave; late and
    # sick_leave stay in the enum so the database column needs no change, but new
    # records cannot use them (see schemas.RecordIn) and reports fold them in.
    present = "present"
    late = "late"
    absent = "absent"
    personal_leave = "personal_leave"
    sick_leave = "sick_leave"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    # Store the enum's value ("present"), not its Python name.
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x], validate_strings=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.teacher, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Term(Base):
    __tablename__ = "terms"
    __table_args__ = (
        UniqueConstraint("academic_year", "term_no", name="uq_term"),
        CheckConstraint("term_no BETWEEN 1 AND 3", name="ck_term_no"),
        CheckConstraint("end_date > start_date", name="ck_term_dates"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # Buddhist year, e.g. 2569
    term_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Classroom(Base):
    __tablename__ = "classrooms"
    __table_args__ = (UniqueConstraint("academic_year", "grade_level", "room_no", name="uq_classroom"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    grade_level: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. ม.1
    room_no: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. 1
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def name(self) -> str:
        return f"{self.grade_level}/{self.room_no}"


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[StudentStatus] = mapped_column(
        _enum(StudentStatus, "student_status"), default=StudentStatus.active, nullable=False
    )

    @property
    def full_name(self) -> str:
        return f"{self.prefix}{self.first_name} {self.last_name}"


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("classroom_id", "student_id", name="uq_enroll"),
        Index("ix_enroll_student", "student_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), nullable=False)
    class_number: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    student: Mapped[Student] = relationship()
    classroom: Mapped[Classroom] = relationship()


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Period(Base):
    __tablename__ = "periods"
    __table_args__ = (CheckConstraint("end_time > start_time", name="ck_period_times"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_no: Mapped[int] = mapped_column(SmallInteger, unique=True, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)


class AttendanceSession(TimestampMixin, Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        UniqueConstraint("classroom_id", "session_date", "period_id", name="uq_session"),
        Index("ix_session_date", "session_date"),
        Index("ix_session_report", "term_id", "classroom_id", "subject_id"),
        Index("ix_session_teacher", "teacher_id", "session_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id"), nullable=False)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activity: Mapped[str | None] = mapped_column(Text, nullable=True)

    term: Mapped[Term] = relationship()
    classroom: Mapped[Classroom] = relationship()
    subject: Mapped[Subject] = relationship()
    period: Mapped[Period] = relationship()
    teacher: Mapped[User] = relationship()
    records: Mapped[list["AttendanceRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_record"),
        Index("ix_record_student", "student_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        _enum(AttendanceStatus, "attendance_status"), default=AttendanceStatus.present, nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    session: Mapped[AttendanceSession] = relationship(back_populates="records")
    student: Mapped[Student] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)

    # BigInteger on MySQL; SQLite needs plain INTEGER for autoincrement primary keys.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

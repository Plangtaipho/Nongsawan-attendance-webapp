import os
import tempfile
from datetime import date, time, timedelta

# Point the app at a throwaway SQLite file BEFORE it is imported.
_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["INITIAL_ADMIN_USERNAME"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.deps import today  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Classroom, Enrollment, Period, Role, Student, Subject, Term, User  # noqa: E402
from app.security import hash_password, login_limiter  # noqa: E402

PASSWORD = "password123"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_limiter._failures.clear()
    yield


@pytest.fixture
def seed():
    """Admin, two teachers, a current term around today, one classroom with 3 students, subject, 2 periods."""
    d = today()
    with SessionLocal() as db:
        admin = User(username="admin", full_name="แอดมิน", role=Role.admin, password_hash=hash_password(PASSWORD))
        t1 = User(username="teacher1", full_name="ครูหนึ่ง", password_hash=hash_password(PASSWORD))
        t2 = User(username="teacher2", full_name="ครูสอง", password_hash=hash_password(PASSWORD))
        term = Term(academic_year=d.year + 543, term_no=2, start_date=d - timedelta(days=30), end_date=d + timedelta(days=60), is_current=True)
        room = Classroom(academic_year=d.year + 543, grade_level="ม.1", room_no="1")
        other_room = Classroom(academic_year=d.year + 543, grade_level="ม.1", room_no="2")
        subj = Subject(subject_code="ค21101", name="คณิตศาสตร์ 1")
        p1 = Period(period_no=1, start_time=time(8, 30), end_time=time(9, 20))
        p2 = Period(period_no=2, start_time=time(9, 20), end_time=time(10, 10))
        db.add_all([admin, t1, t2, term, room, other_room, subj, p1, p2])
        db.flush()
        students = []
        for i, (pre, fn, ln) in enumerate([("ด.ช.", "ก้อง", "ใจดี"), ("ด.ญ.", "น้ำ", "สดใส"), ("ด.ช.", "ภู", "มั่นคง")], start=1):
            s = Student(student_code=f"1000{i}", prefix=pre, first_name=fn, last_name=ln)
            db.add(s)
            db.flush()
            db.add(Enrollment(student_id=s.id, classroom_id=room.id, class_number=i))
            students.append(s.id)
        outsider = Student(student_code="20001", prefix="ด.ช.", first_name="นอก", last_name="ห้อง")
        db.add(outsider)
        db.flush()
        db.add(Enrollment(student_id=outsider.id, classroom_id=other_room.id, class_number=1))
        db.commit()
        return {
            "today": d,
            "term_id": term.id,
            "room_id": room.id,
            "other_room_id": other_room.id,
            "subject_id": subj.id,
            "p1": p1.id,
            "p2": p2.id,
            "students": students,
            "outsider": outsider.id,
            "t1": t1.id,
        }


class Api:
    """TestClient wrapper that logs in and sends the CSRF header like the browser does."""

    def __init__(self, username: str | None = None):
        self.c = TestClient(app)
        self.csrf = ""
        if username:
            r = self.login(username, PASSWORD)
            assert r.status_code == 200, r.text

    def login(self, username, password):
        r = self.c.post("/api/auth/login", json={"username": username, "password": password})
        if r.status_code == 200:
            # The page embeds the token in a <meta> tag; read it the same way.
            html = self.c.get("/").text
            self.csrf = html.split('name="csrf-token" content="')[1].split('"')[0]
        return r

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def _h(self, kw):
        kw.setdefault("headers", {})["X-CSRF-Token"] = self.csrf
        return kw

    def post(self, url, **kw):
        return self.c.post(url, **self._h(kw))

    def patch(self, url, **kw):
        return self.c.patch(url, **self._h(kw))

    def put(self, url, **kw):
        return self.c.put(url, **self._h(kw))

    def delete(self, url, **kw):
        return self.c.delete(url, **self._h(kw))


@pytest.fixture
def api():
    return Api


def session_body(seed, statuses=("present", "absent", "late"), period="p1", day: date | None = None, **extra):
    return {
        "classroom_id": seed["room_id"],
        "subject_id": seed["subject_id"],
        "period_id": seed[period],
        "session_date": (day or seed["today"]).isoformat(),
        "topic": "สมการเชิงเส้น",
        "activity": "ทำแบบฝึกหัด",
        "records": [{"student_id": sid, "status": st} for sid, st in zip(seed["students"], statuses)],
        **extra,
    }

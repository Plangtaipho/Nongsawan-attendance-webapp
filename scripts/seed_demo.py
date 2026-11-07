"""Fill an EMPTY database with demo data for trying the system.

Usage:  python -m scripts.seed_demo
Creates: admin / teacher1 (password: demo12345), the current term, 8 periods,
4 subjects, and classrooms ม.1/1 and ม.1/2 with 30 students each.
Refuses to run if any user already exists, so it can never touch real data.
"""
import random
import sys
from datetime import time, timedelta

from sqlalchemy import func, select

from app.database import SessionLocal
from app.deps import today
from app.config import get_settings
from app.models import Classroom, Enrollment, Period, Role, Student, Subject, Term, User
from app.security import hash_password

FIRST = ["ก้อง", "น้ำ", "ภู", "ฟ้า", "ต้น", "แพรว", "บอส", "มายด์", "เจ", "ใบเตย", "โอม", "ปุยฝ้าย", "ไอซ์", "พลอย", "ตะวัน"]
LAST = ["ใจดี", "สดใส", "มั่นคง", "รักเรียน", "แสงทอง", "ศรีสุข", "บุญมา", "ทองดี", "สุขสวัสดิ์", "พรหมมา"]


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            sys.exit("Database already has users; demo seed only runs on an empty database.")
        d = today()
        year = d.year + 543
        pw = hash_password("demo12345")
        db.add_all([
            User(username="admin", full_name="ครูผู้ดูแลระบบ", role=Role.admin, password_hash=pw),
            User(username="teacher1", full_name="ครูสมใจ ตัวอย่าง", password_hash=pw),
            Term(academic_year=year, term_no=2, start_date=d - timedelta(days=30), end_date=d + timedelta(days=120), is_current=True),
            Subject(subject_code="ค21101", name="คณิตศาสตร์พื้นฐาน 1"),
            Subject(subject_code="ว21101", name="วิทยาศาสตร์ 1"),
            Subject(subject_code="ท21101", name="ภาษาไทย 1"),
            Subject(subject_code="อ21101", name="ภาษาอังกฤษ 1"),
        ])
        # The school's day (same as settings.default_periods): 7 x 50 min from 08:40, lunch 12:00-12:30.
        for n, span in enumerate(get_settings().default_periods.split(","), start=1):
            a, b = (time.fromisoformat(t) for t in span.split("-"))
            db.add(Period(period_no=n, start_time=a, end_time=b))
        rnd = random.Random(42)
        code = 10001
        for room_no in ("1", "2"):
            room = Classroom(academic_year=year, grade_level="ม.1", room_no=room_no)
            db.add(room)
            db.flush()
            for i in range(1, 31):
                boy = i % 2 == 1
                st = Student(student_code=str(code), prefix="ด.ช." if boy else "ด.ญ.", first_name=rnd.choice(FIRST), last_name=rnd.choice(LAST))
                db.add(st)
                db.flush()
                db.add(Enrollment(student_id=st.id, classroom_id=room.id, class_number=i))
                code += 1
        db.commit()
        print("Demo data created. Log in as admin / demo12345 or teacher1 / demo12345")


if __name__ == "__main__":
    main()

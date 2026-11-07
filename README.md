# ระบบเช็คชื่อนักเรียนรายคาบ (School Attendance)

Web App ให้ครูเช็คชื่อนักเรียนรายคาบ/รายวิชาผ่านมือถือ บันทึกหัวข้อที่สอน ดูสรุปรายวัน และพิมพ์รายงานรายเทอมเป็น PDF

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic
- **Frontend:** HTML + CSS + JavaScript (ไม่มี build step) ส่งออกจาก FastAPI ด้วย Jinja2
- **Database:** MySQL 8 / TiDB Cloud (MySQL-compatible) บน Production, SQLite ตอนพัฒนาในเครื่อง
- **Hosting:** Render (Web Service ตัวเดียว)

## โครงสร้างโปรเจกต์

```
app/
  main.py            สร้าง FastAPI app, middleware (session, security headers), error handlers
  config.py          อ่านค่าจาก Environment Variables
  database.py        engine + session ของ SQLAlchemy
  models.py          ตารางทั้งหมด (users, terms, classrooms, students, enrollments,
                     subjects, periods, attendance_sessions, attendance_records, audit_logs)
  schemas.py         Pydantic schemas สำหรับตรวจข้อมูลขาเข้า
  security.py        bcrypt, CSRF token, จำกัดการ Login ผิด
  deps.py            dependency: ผู้ใช้ปัจจุบัน, ตรวจสิทธิ์ admin, ตรวจ CSRF
  routers/           auth, admin, attendance, reports (API) และ pages (หน้าเว็บ)
  services/          logic: นำเข้า Excel, รายงาน, audit log, query ที่ใช้ร่วมกัน
  templates/         หน้า HTML (Jinja2)
  static/            CSS และ JavaScript
alembic/             database migrations
scripts/             seed_demo.py (ข้อมูลทดลอง), create_admin.py
tests/               Pytest (API ทั้งหมด)
e2e/                 Playwright ทดสอบ flow บนจอมือถือ
render.yaml          ตั้งค่า Deploy บน Render
```

## รันในเครื่อง (Development)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                 # ใช้ SQLite เป็นค่าเริ่มต้น
alembic upgrade head                 # สร้างตาราง
python -m scripts.seed_demo          # ข้อมูลทดลอง: admin / demo12345, teacher1 / demo12345
uvicorn app.main:app --reload
```

เปิด http://localhost:8000 (หน้าเว็บ) และ http://localhost:8000/docs (Swagger API, ปิดอัตโนมัติบน Production)

## ทดสอบ

```bash
pytest -q                                            # API tests (ใช้ SQLite ชั่วคราว)
# E2E: เปิด server ที่มีข้อมูลทดลองไว้ก่อน แล้ว
BASE_URL=http://localhost:8000 node e2e/mobile_flow.cjs   # ต้องมี playwright ใน Node
```

## Deploy ขึ้นใช้งานจริง (Render + TiDB Cloud)

### 1. สร้างฐานข้อมูล TiDB Cloud Starter (ฟรี)
1. สมัครที่ https://tidbcloud.com แล้วสร้าง **Starter** instance เลือก Region ใกล้ไทย (เช่น Singapore)
2. กด **Connect** เลือก Connect with = `General`, Operating System = `Debian/Ubuntu` แล้วสร้างรหัสผ่าน
3. คัดลอกค่า Host, Port (4000), User (เช่น `xxxx.root`), Password
4. เปิด SQL Editor แล้วรัน `CREATE DATABASE school_attendance;`
5. ประกอบ URL: `mysql+pymysql://USER:PASSWORD@HOST:4000/school_attendance`
   (ถ้ารหัสผ่านมีอักขระพิเศษ เช่น `@ / :` ต้อง URL-encode ก่อน)

### 2. เอาโค้ดขึ้น GitHub
Push repository นี้ขึ้น GitHub (ไฟล์ `.env` ถูก ignore ไว้แล้ว ห้ามใส่รหัสผ่านในโค้ด)

### 3. สร้าง Web Service บน Render
1. สมัคร https://render.com แล้วเลือก **New → Blueprint** และเลือก repository นี้ (Render อ่าน `render.yaml`)
2. กรอก Environment Variables ที่ถูกถาม:

| ตัวแปร | ค่า |
| --- | --- |
| `DATABASE_URL` | URL จากขั้นที่ 1 |
| `SCHOOL_NAME` | ชื่อโรงเรียน (แสดงบนหน้าเว็บและรายงาน) |
| `INITIAL_ADMIN_USERNAME` | ชื่อผู้ใช้ Admin คนแรก |
| `INITIAL_ADMIN_PASSWORD` | รหัสผ่าน Admin คนแรก (8 ตัวขึ้นไป) |

`SECRET_KEY` Render สุ่มให้เอง, `DB_SSL_CA` ตั้งไว้เป็น CA ของระบบแล้ว (TiDB บังคับ TLS)

3. กด Apply แล้วรอ Build เสร็จ ระหว่าง Start ระบบจะรัน `alembic upgrade head` สร้างตารางให้เอง

### 4. ตรวจสอบหลัง Deploy
1. เปิด `https://<ชื่อ service>.onrender.com/healthz` ต้องได้ `{"status":"ok"}`
2. Login ด้วย Admin คนแรก แล้ว**เปลี่ยนรหัสผ่านทันที** ที่หน้า "บัญชีของฉัน"
3. ไปที่ "ตั้งค่าระบบ": สร้างภาคเรียน (ติ๊กเป็นเทอมปัจจุบัน), คาบเรียน, รายวิชา, บัญชีครู
4. ไปที่ "จัดการนักเรียน": ดาวน์โหลดไฟล์ตัวอย่าง กรอกรายชื่อ แล้วนำเข้า
5. ทดลองเช็คชื่อ 1 คาบบนมือถือ ดูสรุปรายวัน และพิมพ์รายงาน PDF

### ข้อจำกัดของแผนฟรี (ตรวจสอบเมื่อ พ.ย. 2569)
- **Render Free:** หยุดทำงานเมื่อไม่มีคนใช้ 15 นาที คนแรกที่เข้าต้องรอประมาณ 1 นาที, ได้ 750 ชั่วโมง/เดือน, ไม่มี Shell
  ([render.com/docs/free](https://render.com/docs/free)) สำหรับใช้งานจริงทั้งโรงเรียนแนะนำอัปเกรดเป็นแผนเสียเงิน
- **TiDB Cloud Starter:** ฟรี 5 GiB และ 50 ล้าน Request Units ต่อเดือนต่อ instance ถ้าเกินโควตาจะเชื่อมต่อใหม่ไม่ได้จนกว่าจะขึ้นเดือนใหม่
  ([docs.pingcap.com](https://docs.pingcap.com/tidbcloud/select-cluster-tier)) ควรดูยอดใช้งานใน Console สัปดาห์แรก

### Backup
TiDB Cloud มี backup อัตโนมัติตามแผน นอกจากนั้นควรพิมพ์/บันทึกรายงาน PDF ทุกสิ้นเทอม
และ export ข้อมูลจาก TiDB Console (Export) อย่างน้อยเดือนละครั้ง

## ความปลอดภัยที่ทำไว้
- รหัสผ่านเก็บเป็น bcrypt hash, จำกัด Login ผิด 5 ครั้ง/15 นาที ต่อชื่อผู้ใช้+IP
- Session cookie แบบ HttpOnly, SameSite=Lax, Secure (บน Production), เปลี่ยน session ใหม่ทุกครั้งที่ Login
- CSRF token ในทุกคำขอที่แก้ไขข้อมูล, ตรวจสิทธิ์ฝั่ง Server ทุก API
- Content-Security-Policy, X-Frame-Options, HSTS, ไม่แสดง error ภายในให้ผู้ใช้เห็น
- SQLAlchemy ใช้ parameterized query, หน้าเว็บสร้าง DOM ด้วย textContent (กัน XSS)
- ไฟล์นำเข้า: เฉพาะ .xlsx ไม่เกิน 2 MB, ตรวจทุกแถวก่อนบันทึก
- Audit log บันทึกการสร้าง/แก้ไขการเช็คชื่อ การนำเข้า และการแก้ข้อมูลผู้ใช้

ยังไม่ได้ทำ (Phase 2): Login ด้วย Google, ผูกตารางสอน, export Excel, PDF ฝั่ง Server, rate limit ที่ใช้ร่วมกันหลาย instance

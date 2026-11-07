# PROJECT STATUS: ระบบเช็คชื่อนักเรียนรายคาบ

อัปเดต: 7 พ.ย. 2569 · เป้าหมาย: ครูใช้งานจริงวันจันทร์ 9 พ.ย. 2569 (MVP)

## สถานะ

| งาน | สถานะ |
| --- | --- |
| แผนโปรเจกต์, Requirements, ER Diagram | Approved (เลือก "MVP ใช้จริง 9/11") |
| Database schema + Alembic migration | Implemented, Tested บน SQLite; สร้าง DDL ของ MySQL แล้ว ยังไม่ได้รันกับ MySQL/TiDB จริง |
| Backend API (auth, admin, import, attendance, reports) | Implemented, Tested (pytest 38 ข้อผ่าน) |
| Frontend 9 หน้า | Implemented, Tested (Playwright บนจอ Pixel 7 ผ่าน) |
| รายงาน PDF | Implemented, Tested (A4 แนวนอน, ภาษาไทยถูกต้อง, ~41 คน/หน้า) |
| Deploy Render + TiDB Cloud | Deployed + Tested 7 พ.ย. 2569: flow เต็มบน Production ผ่าน (e2e/production_smoke.cjs) และลบข้อมูลทดสอบแล้ว |

## สมมติฐานที่ใช้ (ยังรอผู้ใช้ยืนยัน)
1. ครูเลือกห้อง/คาบ/วิชาเองอิสระ ยังไม่ผูกตารางสอน
2. สถานะ: มา, สาย, ขาด, ลากิจ, ลาป่วย; ร้อยละเข้าเรียน = (มา + สาย) ÷ คาบที่บันทึก
3. ครูแก้ได้เฉพาะคาบที่ตัวเองบันทึก, Admin แก้/ลบได้ทุกคาบ, มี audit log
4. ไฟล์ Excel: เลขประจำตัว, คำนำหน้า, ชื่อ, นามสกุล, ชั้น, ห้อง, เลขที่
5. ติดตั้งแยกโรงเรียนละ 1 ระบบ
6. Login ด้วย Username/Password, Google Login เป็น Phase 2

## ความเสี่ยงที่รู้อยู่
- Render Free หลับหลังไม่มีคนใช้ 15 นาที (รอ ~1 นาที)
- TiDB Starter: ถ้าเกินโควตา 50M RU/เดือน จะเชื่อมต่อใหม่ไม่ได้
- Migration บน TiDB ผ่านแล้ว (7 พ.ย.)
- เลขประจำตัวที่ขึ้นต้นด้วย 0 ต้องเก็บเป็น Text ใน Excel ไม่เช่นนั้น Excel จะตัดเลข 0 ทิ้ง

## Phase 2
Google Login, ตารางสอน, export Excel, PDF ฝั่ง Server, เลื่อนชั้นแบบกลุ่ม, ปรับโลโก้โรงเรียน

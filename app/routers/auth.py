"""Login, logout, current user, change password."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, verify_csrf
from app.models import User
from app.schemas import ChangePasswordIn, LoginIn, UserOut
from app.security import DUMMY_HASH, hash_password, login_limiter, new_csrf_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    key = f"{body.username.lower()}|{ip}"
    if login_limiter.is_blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "เข้าสู่ระบบผิดหลายครั้ง กรุณารอ 15 นาทีแล้วลองใหม่")

    user = db.scalar(select(User).where(User.username == body.username))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not ok or not user.is_active:
        login_limiter.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    login_limiter.reset(key)
    request.session.clear()  # new session on login (prevents session fixation)
    request.session["user_id"] = user.id
    request.session["csrf"] = new_csrf_token()
    return user


@router.post("/logout", status_code=204, dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    request.session.clear()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204, dependencies=[Depends(verify_csrf)])
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "รหัสผ่านปัจจุบันไม่ถูกต้อง")
    user.password_hash = hash_password(body.new_password)
    db.commit()

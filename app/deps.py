"""Shared FastAPI dependencies: current user, admin check, CSRF check."""
import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Role, User


def today() -> date:
    """Today's date in the school's time zone (the server itself runs in UTC)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        return None
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "กรุณาเข้าสู่ระบบ")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "เฉพาะผู้ดูแลระบบเท่านั้น")
    return user


def verify_csrf(request: Request) -> None:
    """State-changing API calls must echo the session's CSRF token in a header."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = request.session.get("csrf")
    sent = request.headers.get("X-CSRF-Token", "")
    if not expected or not secrets.compare_digest(expected, sent):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "คำขอไม่ถูกต้อง กรุณารีเฟรชหน้าแล้วลองใหม่")

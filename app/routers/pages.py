"""Server-rendered HTML pages. Data is loaded by each page's JavaScript from /api/*."""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_optional_user
from app.models import Role, User
from app.routers.reports import load_term_report
from app.security import new_csrf_token

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _find_logo() -> str:
    """URL of the school logo if one was added as static/img/logo.(png|jpg|webp|svg), else ""."""
    for ext in ("png", "webp", "jpg", "svg"):
        f = STATIC_DIR / "img" / f"logo.{ext}"
        if f.exists():
            return f"/static/img/logo.{ext}?v={int(f.stat().st_mtime)}"
    return ""


LOGO_URL = _find_logo()

THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
STATUS_LABELS = {"present": "มา", "leave": "ลา", "absent": "ขาด"}
STATUS_MARKS = {"present": "/", "leave": "ล", "absent": "ข"}


def thai_date(value: str | date, short: bool = True) -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    year = d.year + 543
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {str(year)[2:] if short else year}"


TEMPLATES.env.filters["thai_date"] = thai_date
TEMPLATES.env.globals.update(STATUS_LABELS=STATUS_LABELS, STATUS_MARKS=STATUS_MARKS)

router = APIRouter(include_in_schema=False)


def render(request: Request, name: str, user: User | None, **ctx):
    if user is not None and "csrf" not in request.session:
        request.session["csrf"] = new_csrf_token()
    return TEMPLATES.TemplateResponse(
        request,
        name,
        {
            "user": user,
            "is_admin": bool(user and user.role == Role.admin),
            "csrf_token": request.session.get("csrf", ""),
            "school_name": get_settings().school_name,
            "logo_url": LOGO_URL,
            **ctx,
        },
    )


def _login_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


def page(template: str, admin_only: bool = False, active: str = ""):
    def handler(request: Request, user: User | None = Depends(get_optional_user)):
        if user is None:
            return _login_redirect(request)
        if admin_only and user.role != Role.admin:
            return RedirectResponse("/", status_code=303)
        return render(request, template, user, active=active)

    return handler


router.add_api_route("/", page("attendance.html", active="attendance"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/history", page("history.html", active="history"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/dashboard", page("dashboard.html", active="dashboard"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/reports", page("reports.html", active="reports"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/account", page("account.html", active="account"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/admin/students", page("admin/students.html", True, "students"), methods=["GET"], response_class=HTMLResponse)
router.add_api_route("/admin/settings", page("admin/settings.html", True, "settings"), methods=["GET"], response_class=HTMLResponse)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", None)


# Report columns per printed page; longer terms continue on the next sheet.
PRINT_COLUMNS = 25


@router.get("/reports/term/print", response_class=HTMLResponse)
def term_print(
    request: Request,
    term_id: int,
    classroom_id: int,
    subject_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if user is None:
        return _login_redirect(request)
    report = load_term_report(db, term_id, classroom_id, subject_id)
    sessions = report["sessions"]
    chunks = [list(range(i, min(i + PRINT_COLUMNS, len(sessions)))) for i in range(0, len(sessions), PRINT_COLUMNS)] or [[]]
    return render(request, "report_print.html", user, report=report, chunks=chunks, printed_on=thai_date(date.today(), short=False))

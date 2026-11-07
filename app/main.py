"""FastAPI application: middleware, routers, error handlers, first-admin bootstrap."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.models import Role, User
from app.routers import admin, attendance, auth, pages, reports
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
settings = get_settings()


def bootstrap_admin() -> None:
    """Create the first admin from env vars when there are no users yet (Render free has no shell)."""
    if not (settings.initial_admin_username and settings.initial_admin_password):
        return
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        db.add(
            User(
                username=settings.initial_admin_username,
                full_name=settings.initial_admin_full_name,
                role=Role.admin,
                password_hash=hash_password(settings.initial_admin_password),
            )
        )
        db.commit()
        log.info("Created first admin user %s", settings.initial_admin_username)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.is_production and settings.secret_key == "dev-only-change-me":
        raise RuntimeError("SECRET_KEY must be set in production")
    bootstrap_admin()
    yield


app = FastAPI(
    title="School Attendance API",
    version="1.0.0",
    lifespan=lifespan,
    # API docs only outside production, so the API surface is not advertised publicly.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="sa_session",
    max_age=settings.session_max_age_hours * 3600,
    same_site="lax",
    https_only=settings.is_production,
)

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if not request.url.path.startswith(("/docs", "/openapi.json")):
        response.headers.setdefault("Content-Security-Policy", CSP)
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        msg = str(e.get("msg", "")).removeprefix("Value error, ")
        field = ".".join(str(p) for p in e.get("loc", [])[1:])
        msgs.append(f"{field}: {msg}" if field and not msg.startswith(("รหัสผ่าน", "วัน", "เวลา", "มี")) else msg)
    return JSONResponse({"detail": "ข้อมูลไม่ถูกต้อง: " + "; ".join(msgs[:3])}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง"}, status_code=500)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(attendance.router)
app.include_router(reports.router)
app.include_router(pages.router)

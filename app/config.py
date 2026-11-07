"""Application settings, read from environment variables (or a local .env file)."""
from datetime import time
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" or "production". Production turns on secure cookies and hides API docs.
    env: str = "development"

    # SQLAlchemy URL. Local default is SQLite; production uses MySQL, e.g.
    # mysql+pymysql://user:password@host:3306/school_attendance
    database_url: str = "sqlite:///./dev.db"

    # Path to a CA certificate for TLS connections to a managed MySQL service.
    # Leave empty for SQLite or for a database that does not need it.
    db_ssl_ca: str = ""

    # Long random string used to sign session cookies. MUST be set in production.
    secret_key: str = "dev-only-change-me"

    session_max_age_hours: int = 12
    timezone: str = "Asia/Bangkok"
    school_name: str = "โรงเรียน"

    # When the users table is empty at startup, an admin is created from these values.
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    initial_admin_full_name: str = "ผู้ดูแลระบบ"

    # When the periods table is empty at startup, these periods are created: comma-separated
    # "N=HH:MM-HH:MM" (period number = start-end). Default for this school: 7 slots of which
    # slot 4 is lunch, so teaching periods are 1-3 in the morning and 5-7 in the afternoon.
    default_periods: str = "1=08:40-09:40,2=09:40-10:40,3=10:40-11:40,5=12:30-13:30,6=13:30-14:30,7=14:30-15:30"

    # Sign in with Google (OpenID Connect). Turned on only when both id and secret are set.
    # Only users whose e-mail an admin has entered can sign in; no account is ever created.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Optional: only accept accounts of this Google Workspace domain, e.g. "school.ac.th".
    google_allowed_domain: str = ""

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


def parse_periods(spec: str) -> list[tuple[int, time, time]]:
    """'1=08:40-09:30,2=...' -> [(1, 08:40, 09:30), ...]. Entries without 'N=' are numbered in order."""
    result = []
    for i, item in enumerate(x.strip() for x in spec.split(",") if x.strip()):
        no, _, span = item.rpartition("=")
        start, end = (time.fromisoformat(t.strip()) for t in span.split("-"))
        result.append((int(no) if no else i + 1, start, end))
    return result


@lru_cache
def get_settings() -> Settings:
    return Settings()

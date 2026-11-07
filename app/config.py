"""Application settings, read from environment variables (or a local .env file)."""
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

    # When the periods table is empty at startup, these periods are created (comma-separated HH:MM-HH:MM).
    # Default: 7 periods of 50 minutes, from 08:40, lunch 12:00-12:30.
    default_periods: str = "08:40-09:30,09:30-10:20,10:20-11:10,11:10-12:00,12:30-13:20,13:20-14:10,14:10-15:00"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

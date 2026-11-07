"""Database engine and session factory."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def build_engine(url: str, ssl_ca: str = ""):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Managed MySQL services close idle connections; recycle before they do.
        kwargs["pool_recycle"] = 280
        if ssl_ca:
            kwargs["connect_args"] = {"ssl": {"ca": ssl_ca}}
    return create_engine(url, **kwargs)


_settings = get_settings()
engine = build_engine(_settings.database_url, _settings.db_ssl_ca)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

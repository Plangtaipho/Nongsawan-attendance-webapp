"""Alembic migration environment. Uses the app's own engine settings."""
from logging.config import fileConfig

import sys

from alembic import context
from sqlalchemy.engine import make_url

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import get_settings
from app.database import Base, build_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _check_url(raw: str) -> None:
    """Fail early with a readable message if DATABASE_URL is malformed (password hidden)."""
    url = make_url(raw)
    if url.get_backend_name() != "mysql":
        return
    host_ok = bool(url.host) and "@" not in url.host and " " not in url.host
    # Print only the host part; never the password or anything that may contain it.
    print(f"[migrate] database host = {url.host if host_ok else '(invalid)'}, port = {url.port}", flush=True)
    if not host_ok:
        sys.exit(
            "[migrate] DATABASE_URL has no valid host. Expected "
            "mysql+pymysql://USER:PASSWORD@HOST:4000/DBNAME "
            "(if the password contains @ : / ? # % encode it or reset it to letters and digits)."
        )


def run_migrations_online() -> None:
    _check_url(settings.database_url)
    engine = build_engine(settings.database_url, settings.db_ssl_ca)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

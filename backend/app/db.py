from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import config


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Sempre grava/lê datetimes com fuso UTC (SQLite não preserva tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(url: str | None = None):
    url = url or config.database_url
    if url.startswith("sqlite"):
        if ":memory:" not in url:
            path = url.split("///", 1)[-1]
            if path:
                import pathlib

                pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_con, _):  # noqa: ANN001
            cur = dbapi_con.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return eng
    # PostgreSQL: pool com verificação (sobrevive a reinício do banco)
    return create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def rebind(url: str) -> None:
    """Usado pelos testes para apontar para outro banco."""
    global engine
    engine.dispose()
    engine = make_engine(url)
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

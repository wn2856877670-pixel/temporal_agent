from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import PROJECT_ROOT, Settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_ENGINES: dict[Path, Engine] = {}
_SESSION_FACTORIES: dict[Path, sessionmaker[Session]] = {}


def resolve_database_path(settings: Settings) -> Path:
    path = settings.database_path
    if not path.is_absolute():
        return PROJECT_ROOT / path
    return path


def get_engine(settings: Settings) -> Engine | None:
    if not settings.database_enabled:
        return None
    if settings.database_type.lower() != "sqlite":
        logger.warning("Unsupported database type configured: %s", settings.database_type)
        return None

    path = resolve_database_path(settings)
    if path not in _ENGINES:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ENGINES[path] = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
            future=True,
        )
    return _ENGINES[path]


def init_database(settings: Settings) -> None:
    try:
        engine = get_engine(settings)
        if engine is None:
            return
        from . import models  # noqa: F401

        Base.metadata.create_all(engine)
    except Exception:
        logger.exception("Failed to initialize SQLite database")


def create_session(settings: Settings) -> Session | None:
    try:
        engine = get_engine(settings)
        if engine is None:
            return None
        path = resolve_database_path(settings)
        if path not in _SESSION_FACTORIES:
            _SESSION_FACTORIES[path] = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return _SESSION_FACTORIES[path]()
    except Exception:
        logger.exception("Failed to create SQLite session")
        return None

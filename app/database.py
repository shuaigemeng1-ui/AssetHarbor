"""SQLAlchemy engine, session factory and declarative base."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate() -> None:
    """Idempotent schema migrations for SQLite (create_all does not ALTER)."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(images)"))}
        if "team_id" not in cols:
            conn.execute(
                text("ALTER TABLE images ADD COLUMN team_id INTEGER REFERENCES teams(id)")
            )


def init_db() -> None:
    """Create tables if they do not exist yet, then apply migrations."""
    from . import models  # noqa: F401  (register the models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _migrate()

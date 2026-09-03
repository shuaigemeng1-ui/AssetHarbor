"""SQLAlchemy engine, session factory and declarative base."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings
from .migrations import apply_migrations


class Base(DeclarativeBase):
    pass


def _build_engine():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={
            "check_same_thread": False,
            "timeout": settings.sqlite_busy_timeout_ms / 1000,
        },
    )


engine = _build_engine()


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    """Apply durability/concurrency settings to every SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=268435456")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate() -> None:
    """Apply all versioned schema migrations (idempotent and recorded)."""
    with engine.begin() as conn:
        apply_migrations(conn, Base.metadata)


def init_db() -> None:
    """Create tables if they do not exist yet, then apply migrations."""
    from .. import models  # noqa: F401  (register the models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _migrate()

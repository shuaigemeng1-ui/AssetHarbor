"""SQLAlchemy engine, session factory and declarative base."""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


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
    cursor.close()


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
        user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        if user_cols and "auth_version" not in user_cols:
            conn.execute(
                text(
                    """
                    -- 认证版本：递增后撤销此前签发的 JWT；不使用外键
                    ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 1
                    """
                )
            )

        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(images)"))}
        if "team_id" not in cols:
            conn.execute(
                text("ALTER TABLE images ADD COLUMN team_id INTEGER REFERENCES teams(id)")
            )
        if "signing_version" not in cols:
            conn.execute(
                text("ALTER TABLE images ADD COLUMN signing_version INTEGER NOT NULL DEFAULT 1")
            )
        if "media_kind" not in cols:
            conn.execute(
                text(
                    """
                    -- 媒体类型：image 为历史图片，video 为视频
                    ALTER TABLE images ADD COLUMN media_kind VARCHAR(16) NOT NULL DEFAULT 'image'
                    """
                )
            )

        # SQLite does not persist SQLAlchemy column comments.  Keep the raw,
        # idempotent DDL here with Chinese field comments so installations that
        # bootstrap without ORM metadata retain an auditable schema definition.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS upload_sessions (
                    upload_id VARCHAR(36) NOT NULL PRIMARY KEY, -- 上传会话唯一标识
                    owner_id INTEGER NOT NULL,                 -- 上传用户编号
                    team_id INTEGER,                           -- 所属团队编号（不使用外键）
                    original_filename VARCHAR(255) NOT NULL,   -- 原始文件名
                    name VARCHAR(255) NOT NULL DEFAULT '',     -- 展示名称
                    visibility VARCHAR(16) NOT NULL,           -- 可见性：public/private
                    size BIGINT NOT NULL,                      -- 视频总字节数
                    chunk_size BIGINT NOT NULL,                -- 分片字节数
                    total_parts INTEGER NOT NULL,              -- 分片总数
                    fingerprint VARCHAR(64) NOT NULL,          -- 快速文件指纹
                    status VARCHAR(24) NOT NULL,               -- 会话状态
                    expires_at DATETIME NOT NULL,              -- 会话过期时间
                    final_code VARCHAR(32),                    -- 完成后的视频短码
                    resume_info TEXT NOT NULL DEFAULT '',      -- 崩溃恢复信息（JSON）
                    created_at DATETIME NOT NULL,              -- 创建时间
                    updated_at DATETIME NOT NULL,              -- 最后更新时间
                    completed_at DATETIME                      -- 完成时间
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS upload_parts (
                    id INTEGER NOT NULL PRIMARY KEY,           -- 分片记录编号
                    upload_id VARCHAR(36) NOT NULL,             -- 上传会话标识（不使用外键）
                    part_number INTEGER NOT NULL,               -- 从零开始的分片序号
                    offset BIGINT NOT NULL,                     -- 写入文件的字节偏移
                    size BIGINT NOT NULL,                       -- 分片实际字节数
                    sha256 VARCHAR(64) NOT NULL,                -- 分片 SHA-256
                    created_at DATETIME NOT NULL,               -- 分片落盘时间
                    CONSTRAINT uq_upload_part UNIQUE (upload_id, part_number)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_upload_sessions_owner_id ON upload_sessions (owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_upload_sessions_team_id ON upload_sessions (team_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_upload_sessions_expires_at ON upload_sessions (expires_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_upload_parts_upload_id ON upload_parts (upload_id)"))

        # 媒体分组采用应用层生命周期管理，两个新表均不声明外键。
        # 每个字段都保留中文注释，方便其他数据库方言迁移时直接复用。
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS media_groups (
                    id INTEGER NOT NULL PRIMARY KEY,                 -- 媒体分组编号
                    owner_id INTEGER NOT NULL,                       -- 分组创建用户编号（不使用外键）
                    team_id INTEGER,                                 -- 所属团队编号，空值表示个人分组（不使用外键）
                    name VARCHAR(100) NOT NULL,                      -- 分组名称
                    description VARCHAR(500) NOT NULL DEFAULT '',   -- 分组说明
                    color VARCHAR(16) NOT NULL DEFAULT '#2563eb',   -- 分组主题颜色
                    sort_order INTEGER NOT NULL DEFAULT 0,           -- 分组排序值
                    created_at DATETIME NOT NULL,                    -- 创建时间
                    updated_at DATETIME NOT NULL                     -- 最后更新时间
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS media_group_items (
                    id INTEGER NOT NULL PRIMARY KEY,                 -- 分组成员记录编号
                    group_id INTEGER NOT NULL,                       -- 媒体分组编号（不使用外键）
                    media_id INTEGER NOT NULL,                       -- 媒体资源编号（不使用外键）
                    added_by INTEGER NOT NULL,                       -- 添加操作用户编号（不使用外键）
                    created_at DATETIME NOT NULL,                    -- 加入分组时间
                    CONSTRAINT uq_media_group_item UNIQUE (group_id, media_id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_groups_owner_id ON media_groups (owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_groups_team_id ON media_groups (team_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_group_items_group_id ON media_group_items (group_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_media_group_items_media_id ON media_group_items (media_id)"))


def init_db() -> None:
    """Create tables if they do not exist yet, then apply migrations."""
    from .. import models  # noqa: F401  (register the models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _migrate()

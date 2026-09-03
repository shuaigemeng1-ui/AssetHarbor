"""Versioned SQLite migrations.

The old single ``_migrate()`` body is preserved as migration v1 (idempotent
legacy schema upgrades).  New schema changes are added as explicit versioned
migrations below and recorded in ``schema_migrations`` so every installation
moves forward deterministically instead of re-running an ever-growing
migration monolith.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.sql.elements import TextClause

# Each entry is ``(version, name, function)``; functions receive the open
# transaction connection and the SQLAlchemy metadata of the current models.
MIGRATIONS: list[tuple[int, str, callable]] = []


def _register(version: int, name: str):
    def decorator(func):
        MIGRATIONS.append((version, name, func))
        return func

    return decorator


def _ensure_schema_migrations(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER NOT NULL PRIMARY KEY,   -- 迁移版本号
                name VARCHAR(128) NOT NULL,             -- 迁移名称
                applied_at DATETIME NOT NULL            -- 应用时间
            )
            """
        )
    )


def _applied_versions(conn) -> set[int]:
    return set(conn.execute(text("SELECT version FROM schema_migrations")).scalars().all())


def apply_migrations(conn, metadata) -> None:
    """Apply every not-yet-applied migration inside the caller's transaction."""
    _ensure_schema_migrations(conn)
    applied = _applied_versions(conn)
    for version, name, func in sorted(MIGRATIONS):
        if version in applied:
            continue
        func(conn, metadata)
        conn.execute(
            text(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (:version, :name, :applied_at)
                """
            ),
            {
                "version": version,
                "name": name,
                "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )


# ---------------------------------------------------------------------------
# v1: legacy idempotent schema upgrades (kept from the original _migrate()).
# ---------------------------------------------------------------------------


@_register(1, "legacy-idempotent-schema")
def _migrate_v1(conn, _metadata) -> None:
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
            text("ALTER TABLE images ADD COLUMN team_id INTEGER")
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

    # API 流量只保存低基数日聚合，不记录 URL 查询串、鉴权头或请求内容。
    # 用户和 API Key 删除后历史统计仍可保留，因此所有编号均不声明外键。
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS traffic_daily (
                id INTEGER NOT NULL PRIMARY KEY,                  -- 流量聚合记录编号
                day DATE NOT NULL,                               -- UTC 统计日期
                user_id INTEGER NOT NULL DEFAULT 0,              -- 调用用户编号，0 表示匿名（不使用外键）
                api_key_id INTEGER NOT NULL DEFAULT 0,           -- API Key 编号，0 表示未使用 Key（不使用外键）
                route VARCHAR(160) NOT NULL,                     -- 规范化接口路由模板
                method VARCHAR(8) NOT NULL,                      -- HTTP 请求方法
                request_count BIGINT NOT NULL DEFAULT 0,        -- 接口调用次数
                error_count BIGINT NOT NULL DEFAULT 0,          -- HTTP 4xx/5xx 调用次数
                request_bytes BIGINT NOT NULL DEFAULT 0,        -- 请求体累计字节数
                response_bytes BIGINT NOT NULL DEFAULT 0,       -- 响应体累计字节数
                created_at DATETIME NOT NULL,                    -- 首次统计时间
                updated_at DATETIME NOT NULL,                    -- 最后聚合时间
                CONSTRAINT uq_traffic_daily_dimension UNIQUE
                    (day, user_id, api_key_id, route, method)
            )
            """
        )
    )
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_traffic_daily_day ON traffic_daily (day)")
    )
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_traffic_daily_user_id ON traffic_daily (user_id)")
    )
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_traffic_daily_api_key_id ON traffic_daily (api_key_id)")
    )

    # 持久高水位避免 SQLite 在删除 API Key 后复用整数主键；不声明外键。
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS runtime_counters (
                name VARCHAR(64) NOT NULL PRIMARY KEY, -- 计数器名称
                value BIGINT NOT NULL DEFAULT 0,       -- 当前高水位值
                updated_at DATETIME NOT NULL           -- 最后更新时间
            )
            """
        )
    )
    # 升级旧库时先用现存最大用户编号初始化高水位；后续删除用户不回退。
    # 极早期兼容库可能只有 images 表，因此先确认 users 确实存在。
    table_names = set(inspect(conn).get_table_names())
    if "users" in table_names:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO runtime_counters (name, value, updated_at)
                SELECT 'user_id', COALESCE(MAX(id), 0), CURRENT_TIMESTAMP FROM users
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE runtime_counters
                SET value = MAX(value, (SELECT COALESCE(MAX(id), 0) FROM users)),
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = 'user_id'
                """
            )
        )
    # API Key 的控制面 URL 同样要求编号永不复用。升级时必须在任何
    # revoke/rotate 发生前，同时吸收存活 Key 与保留流量历史的最高编号。
    table_names = set(inspect(conn).get_table_names())
    if "api_keys" in table_names:
        historical_expression = (
            "(SELECT COALESCE(MAX(api_key_id), 0) FROM traffic_daily)"
            if "traffic_daily" in table_names
            else "0"
        )
        api_key_high_water_sql = (
            "MAX((SELECT COALESCE(MAX(id), 0) FROM api_keys), "
            f"{historical_expression})"
        )
        conn.execute(
            text(
                f"""
                INSERT OR IGNORE INTO runtime_counters (name, value, updated_at)
                SELECT 'api_key_id', {api_key_high_water_sql}, CURRENT_TIMESTAMP
                """
            )
        )
        conn.execute(
            text(
                f"""
                UPDATE runtime_counters
                SET value = MAX(value, {api_key_high_water_sql}),
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = 'api_key_id'
                """
            )
        )

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

    # 对外暴露的整数资源编号使用持久高水位，避免删除后 SQLite 复用编号，
    # 从而让迟到的 PATCH/DELETE 重试误操作刚创建的团队、成员或分组。
    # 旧测试库可能不含历史团队表，因此仅初始化实际存在的固定表名。
    table_names = set(inspect(conn).get_table_names())
    for counter_name, table_name in (
        ("team_id", "teams"),
        ("team_member_id", "team_members"),
        ("media_group_id", "media_groups"),
    ):
        if table_name not in table_names:
            continue
        conn.execute(
            text(
                f"""
                INSERT OR IGNORE INTO runtime_counters (name, value, updated_at)
                SELECT :counter_name, COALESCE(MAX(id), 0), CURRENT_TIMESTAMP
                FROM {table_name}
                """
            ),
            {"counter_name": counter_name},
        )
        conn.execute(
            text(
                f"""
                UPDATE runtime_counters
                SET value = MAX(value, (SELECT COALESCE(MAX(id), 0) FROM {table_name})),
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = :counter_name
                """
            ),
            {"counter_name": counter_name},
        )


# ---------------------------------------------------------------------------
# v2: remove every database foreign key by rebuilding affected tables.
# ---------------------------------------------------------------------------


def _render_default(default) -> str | None:
    if default is None:
        return None
    arg = getattr(default, "arg", default)
    if isinstance(arg, TextClause):
        return str(arg.text)
    if isinstance(arg, str):
        return "'" + arg.replace("'", "''") + "'"
    if isinstance(arg, bool):
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return str(arg)
    return str(arg)


def _column_sql(column) -> str:
    type_sql = str(column.type)
    parts = [f'"{column.name}" {type_sql}']
    if not column.nullable:
        parts.append("NOT NULL")
    if column.primary_key and len(column.table.primary_key.columns) == 1:
        parts.append("PRIMARY KEY")
        if (
            column.table.kwargs.get("sqlite_autoincrement")
            and type_sql.upper() == "INTEGER"
        ):
            parts.append("AUTOINCREMENT")
    if column.unique:
        parts.append("UNIQUE")
    default = _render_default(column.server_default)
    if default is not None:
        parts.append(f"DEFAULT {default}")
    return " ".join(parts)


def _table_constraints_sql(table) -> list[str]:
    constraints = []
    pk = table.primary_key
    if len(pk.columns) > 1:
        cols = ", ".join(f'"{c.name}"' for c in pk.columns)
        constraints.append(f"CONSTRAINT {pk.name or 'pk'} PRIMARY KEY ({cols})")
    for constraint in table.constraints:
        if constraint.__class__.__name__ == "UniqueConstraint":
            cols = ", ".join(f'"{c.name}"' for c in constraint.columns)
            name = constraint.name or "uq"
            constraints.append(f"CONSTRAINT {name} UNIQUE ({cols})")
    return constraints


def _create_table_without_fks(conn, table, new_name: str) -> None:
    column_sql = ",\n    ".join(_column_sql(c) for c in table.columns)
    constraint_sql = _table_constraints_sql(table)
    body = ",\n    ".join([column_sql, *constraint_sql])
    conn.execute(text(f'CREATE TABLE "{new_name}" (\n    {body}\n)'))


@_register(2, "drop-all-foreign-keys")
def _migrate_v2_drop_foreign_keys(conn, metadata) -> None:
    """Rebuild any table that still has FK constraints without them.

    SQLite cannot ``DROP CONSTRAINT``, so affected tables are copied into a
    new no-FK table, the old table is dropped, and the new table is renamed.
    Indexes are recreated afterwards so query performance is preserved.
    """
    inspector = inspect(conn)
    existing = set(inspector.get_table_names())
    table_names = sorted(set(metadata.tables.keys()) & existing)
    for table_name in table_names:
        if not inspector.get_foreign_keys(table_name):
            continue
        table = metadata.tables[table_name]
        existing_cols = {
            row[1] for row in conn.execute(text(f"PRAGMA table_info({table_name})"))
        }
        model_cols = {column.name for column in table.columns}
        if not model_cols.issubset(existing_cols):
            # A partial legacy table cannot be copied into the full model
            # schema.  v1 never adds FKs to such tables, so this is a safety
            # net rather than a normal path.
            continue
        temp_name = f"_migrate_no_fk_{table_name}"
        conn.execute(text(f'DROP TABLE IF EXISTS "{temp_name}"'))
        _create_table_without_fks(conn, table, temp_name)
        columns = ", ".join(f'"{c.name}"' for c in table.columns)
        conn.execute(
            text(f'INSERT INTO "{temp_name}" ({columns}) SELECT {columns} FROM "{table_name}"')
        )
        conn.execute(text(f'DROP TABLE "{table_name}"'))
        conn.execute(text(f'ALTER TABLE "{temp_name}" RENAME TO "{table_name}"'))
        for index in table.indexes:
            index.create(bind=conn, checkfirst=True)
        if table.kwargs.get("sqlite_autoincrement"):
            conn.execute(
                text(
                    f"""
                    INSERT OR REPLACE INTO sqlite_sequence (name, seq)
                    SELECT '{table_name}', COALESCE(MAX(id), 0) FROM "{table_name}"
                    """
                )
            )


# ---------------------------------------------------------------------------
# v3: composite indexes for media queries and gallery ordering.
# ---------------------------------------------------------------------------


@_register(3, "composite-media-indexes")
def _migrate_v3_composite_indexes(conn, _metadata) -> None:
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(images)"))}
    required = {"owner_id", "team_id", "media_kind", "created_at"}
    if not required.issubset(cols):
        return
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_images_owner_composite "
            "ON images (owner_id, team_id, media_kind, created_at, id)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_images_team_composite "
            "ON images (team_id, media_kind, created_at, id)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_images_global_media_created "
            "ON images (media_kind, created_at, id)"
        )
    )


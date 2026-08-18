"""API Key 模型。

只保存密钥的 SHA-256 哈希；数据库不声明外键，用户删除时由服务层显式清理。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="API Key 编号")
    user_id: Mapped[int] = mapped_column(
        Integer, index=True, nullable=False, comment="所属用户编号（不使用外键）"
    )
    name: Mapped[str] = mapped_column(
        String(64), default="", server_default="", nullable=False, comment="Key 名称"
    )
    # SHA-256 hex digest of the key. The plaintext is shown exactly once at
    # creation/rotation and can never be recovered afterwards.
    key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="密钥 SHA-256 哈希（唯一）"
    )
    # First 8 chars of the key, for display/identification only.
    key_prefix: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="密钥前 8 位，仅用于展示"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="创建时间"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近使用时间"
    )

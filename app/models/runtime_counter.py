"""Persistent monotonic counters used where SQLite row IDs must never be reused."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class RuntimeCounter(Base):
    """Small no-foreign-key counter table for durable identifier allocation."""

    __tablename__ = "runtime_counters"

    name: Mapped[str] = mapped_column(String(64), primary_key=True, comment="计数器名称")
    value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="当前高水位值")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow, comment="最后更新时间"
    )

"""Database models.

MVP ships only ``Image``. User / Group / role columns are reserved below and
land with the auth + multi-tenancy milestone.
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Random base62 code used in the public URL: /i/{code}
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Path relative to settings.data_dir, sharded two levels deep, e.g. files/ab/cd/abcdef1234.png
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Reserved for the multi-tenancy milestone:
    # owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)

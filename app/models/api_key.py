"""API key model — stores only a SHA-256 hash of the key."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .base import utcnow
from .user import User


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # SHA-256 hex digest of the key. The plaintext is shown exactly once at
    # creation/rotation and can never be recovered afterwards.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # First 8 chars of the key, for display/identification only.
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")

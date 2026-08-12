"""Database models: User (auth/RBAC) and Image (multi-tenant, named)."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    images: Mapped[list["Image"]] = relationship(back_populates="owner")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Random base62 code used in the public URL: /i/{code}
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Display name chosen by the owner at upload time (falls back to filename).
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # public: anyone with the code can view; private: owner and admins only.
    visibility: Mapped[str] = mapped_column(String(16), default="public", nullable=False)
    # Path relative to settings.data_dir, sharded two levels deep, e.g. files/ab/cd/abcdef1234.png
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Multi-tenancy: images belong to a user (null only for pre-auth legacy rows).
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    owner: Mapped[User | None] = relationship(back_populates="images")

    # Reserved for the groups milestone:
    # group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)

"""Image model — ownership, visibility and team space."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .base import utcnow
from .user import User


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Random base62 code used in the public URL: /i/{code}
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Display name chosen by the owner at upload time (falls back to filename).
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # public: anyone with the code can view; private: owner/admins/team/signed links.
    visibility: Mapped[str] = mapped_column(String(16), default="public", nullable=False)
    # Path relative to settings.data_dir, sharded two levels deep, e.g. files/ab/cd/abcdef1234.png
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    media_kind: Mapped[str] = mapped_column(
        String(16), default="image", server_default="image", nullable=False,
        comment="媒体类型：image 图片、video 视频",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Ownership & team space: an image belongs to a user, optionally in a team.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    # Bumped whenever the image becomes private, revoking previously issued
    # signed links (they embed this version in the HMAC).
    signing_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    owner: Mapped[User | None] = relationship(back_populates="images")

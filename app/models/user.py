"""User account model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .base import utcnow


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="用户编号")
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="登录用户名"
    )
    password_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="密码哈希（不保存明文密码）"
    )
    role: Mapped[str] = mapped_column(
        String(16), default="user", nullable=False, comment="全局角色：user/admin"
    )
    auth_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
        comment="认证版本，递增后撤销此前签发的 JWT",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="账号创建时间"
    )

    images: Mapped[list["Image"]] = relationship(back_populates="owner")
    team_memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")

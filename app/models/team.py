"""团队与团队成员模型。

本模块刻意不声明任何数据库外键；团队、成员和用户的生命周期由服务层显式
维护（删除用户/团队/成员时同步清理或转交），避免历史 SQLite 数据库产生
外键约束和级联删除风险。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="团队编号")
    name: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="团队名称（唯一）"
    )
    description: Mapped[str] = mapped_column(
        String(255), default="", server_default="", nullable=False, comment="团队简介"
    )
    # 团队所有者编号（不使用外键）：仅表示所有权，成员关系以 team_members 为准。
    owner_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="团队所有者用户编号（不使用外键）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="创建时间"
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="成员关系编号")
    team_id: Mapped[int] = mapped_column(
        Integer, index=True, nullable=False, comment="所属团队编号（不使用外键）"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, index=True, nullable=False, comment="成员用户编号（不使用外键）"
    )
    # owner | admin | member
    role: Mapped[str] = mapped_column(
        String(16), default="member", server_default="member", nullable=False, comment="团队角色：owner/admin/member"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="加入时间"
    )

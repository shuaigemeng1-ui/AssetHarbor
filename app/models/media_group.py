"""媒体分组及分组成员模型。

新表刻意不声明数据库外键；资源删除、用户删除和团队解散时由服务层显式
维护生命周期，避免给历史 SQLite 数据库增加外键约束。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class MediaGroup(Base):
    __tablename__ = "media_groups"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="媒体分组编号"
    )
    owner_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="分组创建用户编号（不使用外键）"
    )
    team_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="所属团队编号，空值表示个人分组（不使用外键）"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="分组名称"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="分组说明"
    )
    color: Mapped[str] = mapped_column(
        String(16), nullable=False, default="#2563eb", server_default="#2563eb", comment="分组主题颜色"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="分组排序值"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow, comment="最后更新时间"
    )


class MediaGroupItem(Base):
    __tablename__ = "media_group_items"
    __table_args__ = (
        UniqueConstraint("group_id", "media_id", name="uq_media_group_item"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="分组成员记录编号"
    )
    group_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="媒体分组编号（不使用外键）"
    )
    media_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="媒体资源编号（不使用外键）"
    )
    added_by: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="添加操作用户编号（不使用外键）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, comment="加入分组时间"
    )

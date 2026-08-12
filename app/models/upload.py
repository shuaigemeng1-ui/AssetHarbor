"""Resumable video upload sessions and their persisted chunks.

These tables intentionally contain no foreign keys.  User/team lifecycle
operations explicitly update or remove upload rows, which also makes cleanup
safe for legacy SQLite databases whose foreign-key setting varied by release.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    upload_id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="上传会话唯一标识")
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False, comment="上传用户编号")
    team_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True, comment="所属团队编号")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False, comment="展示名称")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, comment="可见性")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="视频总字节数")
    chunk_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="分片字节数")
    total_parts: Mapped[int] = mapped_column(Integer, nullable=False, comment="分片总数")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, comment="快速文件指纹")
    status: Mapped[str] = mapped_column(String(24), nullable=False, comment="会话状态")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False, comment="会话过期时间")
    final_code: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="完成后的视频短码")
    resume_info: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False, comment="崩溃恢复信息"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="最后更新时间")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")


class UploadPart(Base):
    __tablename__ = "upload_parts"
    __table_args__ = (
        UniqueConstraint("upload_id", "part_number", name="uq_upload_part"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="分片记录编号")
    upload_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False, comment="上传会话标识")
    part_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="从零开始的分片序号")
    offset: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="写入文件的字节偏移")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="分片实际字节数")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, comment="分片 SHA-256")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="分片落盘时间")

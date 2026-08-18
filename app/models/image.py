"""图片/视频媒体模型（统一存储在 images 表）。

该表刻意不声明数据库外键：owner_id 只表示上传者、归因和配额，team_id 只
表示所属团队；访问与生命周期控制全部由应用层按团队权限显式执行。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="媒体资源编号")
    # Random base62 code used in the public URL: /i/{code}
    code: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False, comment="公开短码（URL 中使用）"
    )
    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名"
    )
    # Display name chosen by the owner at upload time (falls back to filename).
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="展示名称"
    )
    # public: anyone with the code can view; private: owner/admins/team/signed links.
    visibility: Mapped[str] = mapped_column(
        String(16), default="public", server_default="public", nullable=False, comment="可见性：public/private"
    )
    # Path relative to settings.data_dir, sharded two levels deep, e.g. files/ab/cd/abcdef1234.png
    stored_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="存储相对路径（两级分片）"
    )
    content_type: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="内容类型（由魔数嗅探得到）"
    )
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件字节数")
    sha256: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="文件 SHA-256"
    )
    media_kind: Mapped[str] = mapped_column(
        String(16),
        default="image",
        server_default="image",
        nullable=False,
        comment="媒体类型：image 图片、video 视频",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, comment="创建时间"
    )

    # Ownership & team space: an image belongs to a user, optionally in a team.
    # 不使用外键；owner_id 仅表示上传者/归因/配额，team_id 非空时由团队权限控制。
    owner_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="上传者用户编号（不使用外键）"
    )
    team_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="所属团队编号（不使用外键）"
    )
    # Bumped whenever the image becomes private or the owner explicitly revokes
    # all signed links (they embed this version in the HMAC).
    signing_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False, comment="签名链接版本，递增即撤销全部历史分享链接"
    )

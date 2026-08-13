"""按日聚合的 API 流量统计模型（不声明外键）。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .base import utcnow


class TrafficDaily(Base):
    """低基数日聚合，避免为每次请求写入一条明细记录。"""

    __tablename__ = "traffic_daily"
    __table_args__ = (
        UniqueConstraint(
            "day",
            "user_id",
            "api_key_id",
            "route",
            "method",
            name="uq_traffic_daily_dimension",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="流量聚合记录编号")
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True, comment="UTC 统计日期")
    # 0 表示匿名调用。保留被删除用户的历史编号，不使用外键。
    user_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True, comment="调用用户编号，0 表示匿名"
    )
    # 0 表示 JWT 或匿名调用。API Key 删除后仍保留历史编号，不使用外键。
    api_key_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True, comment="API Key 编号，0 表示未使用 Key"
    )
    route: Mapped[str] = mapped_column(
        String(160), nullable=False, comment="规范化接口路由模板"
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False, comment="HTTP 请求方法")
    request_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="接口调用次数"
    )
    error_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="HTTP 4xx/5xx 调用次数"
    )
    request_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="请求体累计字节数"
    )
    response_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="响应体累计字节数"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, comment="首次统计时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow, comment="最后聚合时间"
    )

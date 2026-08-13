"""Admin-related schemas."""

from datetime import date

from pydantic import BaseModel, Field


class AdminStats(BaseModel):
    users: int
    images: int
    videos: int
    media_total: int
    teams: int
    storage_bytes: int
    pending_upload_bytes: int
    traffic_request_count: int = 0
    traffic_request_bytes: int = 0
    traffic_response_bytes: int = 0
    traffic_total_bytes: int = 0
    telemetry_complete: bool = Field(
        default=True,
        description="True when the current process has observed no telemetry queue drops; not a cross-restart guarantee",
    )
    telemetry_dropped_events: int = Field(
        default=0,
        description="Telemetry events dropped by the current process since it started",
    )


class TrafficTotals(BaseModel):
    request_count: int
    error_count: int
    request_bytes: int
    response_bytes: int
    total_bytes: int


class TrafficDailyPoint(TrafficTotals):
    date: date


class TrafficRoutePoint(TrafficTotals):
    route: str
    method: str


class TrafficApiKeyPoint(TrafficTotals):
    api_key_id: int
    key_name: str | None = None
    key_prefix: str | None = None
    user_id: int
    username: str | None = None


class MemberUsagePoint(TrafficTotals):
    user_id: int
    username: str
    role: str
    storage_bytes: int
    image_bytes: int
    video_bytes: int
    pending_upload_bytes: int
    total_usage_bytes: int


class AdminTrafficStats(BaseModel):
    telemetry_complete: bool = Field(
        description="True when the current process has observed no telemetry queue drops; not a cross-restart guarantee"
    )
    telemetry_dropped_events: int = Field(
        description="Telemetry events dropped by the current process since it started"
    )
    days: int
    start_date: date
    end_date: date
    summary: TrafficTotals
    anonymous: TrafficTotals
    daily: list[TrafficDailyPoint]
    routes: list[TrafficRoutePoint]
    api_keys: list[TrafficApiKeyPoint]
    members: list[MemberUsagePoint]


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=6, max_length=128)
    role: str = "user"

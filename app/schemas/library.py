"""统一媒体库、分组和概览接口的数据结构。"""

from datetime import datetime

from pydantic import BaseModel, Field


class MediaGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    team_id: int | None = Field(default=None, ge=1)
    codes: list[str] = Field(default_factory=list, max_length=100)


class MediaGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = Field(default=None, ge=-1_000_000, le=1_000_000)


class MediaGroupOut(BaseModel):
    id: int
    name: str
    description: str
    color: str
    sort_order: int
    owner_id: int
    owner_username: str | None = None
    team_id: int | None = None
    item_count: int
    created_at: datetime
    updated_at: datetime


class MediaGroupListResponse(BaseModel):
    items: list[MediaGroupOut]
    total: int


class MediaGroupItemsAdd(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=100)


class UnifiedMediaInfo(BaseModel):
    code: str
    url: str
    size: int
    content_type: str
    sha256: str
    created_at: datetime
    name: str
    visibility: str
    owner_id: int | None
    owner_username: str | None = None
    team_id: int | None = None
    original_filename: str | None
    media_kind: str


class UnifiedMediaLink(BaseModel):
    code: str
    media_kind: str
    visibility: str
    url: str
    expires_at: datetime | None = None


class UnifiedMediaListResponse(BaseModel):
    items: list[UnifiedMediaInfo]
    total: int


class MediaGroupItemsResult(BaseModel):
    added: int
    skipped: int
    group: MediaGroupOut


class LibraryStats(BaseModel):
    scope: str
    images: int
    videos: int
    media_total: int
    storage_bytes: int
    pending_upload_bytes: int
    groups: int
    teams_count: int

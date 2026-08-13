"""Schemas for resumable video uploads and video gallery operations."""

from datetime import datetime

from pydantic import BaseModel, Field


class VideoUploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    name: str = Field(default="", max_length=255)
    visibility: str = "public"
    team_id: int | None = None
    fingerprint: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class VideoUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    visibility: str | None = None


class VideoInfo(BaseModel):
    code: str
    url: str
    size: int
    content_type: str
    sha256: str
    created_at: datetime
    name: str
    visibility: str
    owner_id: int | None
    team_id: int | None = None
    original_filename: str
    owner_username: str | None = None
    media_kind: str = "video"


class VideoListResponse(BaseModel):
    items: list[VideoInfo]
    total: int


class VideoUploadStatus(BaseModel):
    upload_id: str
    filename: str
    size: int
    name: str
    visibility: str
    fingerprint: str
    team_id: int | None = None
    chunk_size: int
    total_parts: int
    status: str
    uploaded_parts: list[int]
    expires_at: datetime
    video: VideoInfo | None = None


class VideoUploadListResponse(BaseModel):
    items: list[VideoUploadStatus]
    total: int
    max_active: int
    part_concurrency: int


class VideoPartResponse(BaseModel):
    part_number: int
    size: int
    sha256: str

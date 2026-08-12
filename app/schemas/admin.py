"""Admin-related schemas."""

from pydantic import BaseModel, Field


class AdminStats(BaseModel):
    users: int
    images: int
    videos: int
    media_total: int
    teams: int
    storage_bytes: int
    pending_upload_bytes: int


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=6, max_length=128)
    role: str = "user"

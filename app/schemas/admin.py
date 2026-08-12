"""Admin-related schemas."""

from pydantic import BaseModel


class AdminStats(BaseModel):
    users: int
    images: int
    videos: int
    media_total: int
    teams: int
    storage_bytes: int
    pending_upload_bytes: int

"""Image-related schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
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


class ImageUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    visibility: str | None = None


class ImageInfo(UploadResponse):
    """Image metadata as returned by the gallery list endpoint."""

    original_filename: str
    owner_username: str | None = None


class ImageListResponse(BaseModel):
    items: list[ImageInfo]
    total: int


class SignedLinkResponse(BaseModel):
    url: str
    expires_at: datetime

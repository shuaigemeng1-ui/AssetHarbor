"""Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel


class UploadResponse(BaseModel):
    code: str
    url: str
    size: int
    content_type: str
    sha256: str
    created_at: datetime


class ImageInfo(UploadResponse):
    """Image metadata as returned by the gallery list endpoint."""

    original_filename: str


class ImageListResponse(BaseModel):
    items: list[ImageInfo]
    total: int


class HealthResponse(BaseModel):
    status: str
    version: str

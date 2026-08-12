"""Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=6, max_length=128)
    invite_code: str | None = None


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


class HealthResponse(BaseModel):
    status: str
    version: str

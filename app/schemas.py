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
    team_id: int | None = None


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


# --- teams -----------------------------------------------------------------


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=255)


class AddMember(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class RoleUpdate(BaseModel):
    role: str


class TeamMemberOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime


class TeamOut(BaseModel):
    id: int
    name: str
    description: str
    role: str  # caller's role in the team: owner | admin | member
    member_count: int
    owner_username: str | None
    created_at: datetime


class TeamDetail(TeamOut):
    members: list[TeamMemberOut]


class TeamAdminOut(BaseModel):
    id: int
    name: str
    description: str
    owner_username: str | None
    member_count: int
    created_at: datetime


class AdminStats(BaseModel):
    users: int
    images: int
    teams: int
    storage_bytes: int


class HealthResponse(BaseModel):
    status: str
    version: str

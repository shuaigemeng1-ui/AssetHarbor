"""Team-related schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


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

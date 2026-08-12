"""Admin-related schemas."""

from pydantic import BaseModel


class AdminStats(BaseModel):
    users: int
    images: int
    teams: int
    storage_bytes: int

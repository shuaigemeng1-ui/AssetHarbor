"""API-key schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(default="", max_length=64)


class ApiKeyOut(BaseModel):
    """Key metadata only — the full key is never returned again."""

    id: int
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(BaseModel):
    """Returned exactly once (create/rotate); carries the plaintext key."""

    id: int
    name: str
    key: str
    key_prefix: str
    created_at: datetime

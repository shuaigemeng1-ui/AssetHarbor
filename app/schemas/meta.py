"""Meta / health schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class PublicConfig(BaseModel):
    """Non-sensitive settings used to keep the login/upload UI honest."""

    version: str
    registration_mode: str
    max_upload_size_mb: int
    max_video_size_mb: int
    video_chunk_size_mb: int
    default_visibility: str

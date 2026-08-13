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
    max_active_video_uploads: int
    video_chunk_concurrency: int
    user_storage_quota_bytes: int
    team_storage_quota_bytes: int

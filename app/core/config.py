"""Application settings, read from environment variables (OSS_* prefix) or a .env file."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OSS_", env_file=".env", extra="ignore")

    app_name: str = "oss"
    version: str = "0.7.0"

    # --- storage -----------------------------------------------------------
    # Base directory for the SQLite database and uploaded files.
    data_dir: Path = Path("./data")

    # --- upload limits -----------------------------------------------------
    max_upload_size_mb: int = Field(default=10, gt=0, le=1024)

    # Video uploads use a resumable, fixed-size chunk protocol.  The defaults
    # deliberately keep individual reverse-proxy requests small while still
    # allowing large source files to be stored without buffering them in RAM.
    max_video_size_mb: int = Field(default=2048, gt=0, le=1024 * 1024)
    video_chunk_size_mb: int = Field(default=8, gt=0, le=1024)
    video_upload_ttl_hours: int = Field(default=24 * 7, gt=0, le=24 * 365)
    max_active_video_uploads: int = Field(default=3, gt=0, le=1000)
    video_chunk_concurrency: int = Field(default=3, ge=1, le=32)
    min_free_space_mb: int = Field(default=1024, ge=0, le=1024 * 1024)
    # Completed media plus unfinished video reservations. Zero means unlimited.
    user_storage_quota_mb: int = Field(default=0, ge=0, le=10_485_760)
    team_storage_quota_mb: int = Field(default=0, ge=0, le=10_485_760)
    video_cleanup_interval_seconds: int = Field(default=60 * 60, gt=0, le=7 * 86400)

    # SQLite lock wait used by both SQLAlchemy and the connection PRAGMA.
    sqlite_busy_timeout_ms: int = Field(default=5000, gt=0, le=300_000)

    # --- short codes -------------------------------------------------------
    # Length (in base62 characters) of the random code used in image URLs.
    short_code_length: int = Field(default=10, ge=6, le=32)

    # --- public URL --------------------------------------------------------
    # Base URL used to build the links returned by the API, e.g.
    # "https://img.example.com". Leave empty to derive it from each request.
    public_url: str = ""

    # --- reverse proxy ------------------------------------------------------
    # Trusted proxy IPs/CIDRs mirrored to Uvicorn via --forwarded-allow-ips.
    # When this keeps its 127.0.0.1 default while a reverse proxy connects
    # from another host/container (e.g. a Docker bridge gateway), Uvicorn
    # ignores X-Forwarded-For and every proxied client shares one rate-limit
    # identity. The app warns at startup in that configuration.
    forwarded_allow_ips: str = "127.0.0.1"

    # --- auth --------------------------------------------------------------
    # Bootstrap password for the built-in "admin" account (empty = skip).
    admin_password: str = ""
    # Registration policy: open | invite | closed
    # Closed by default now that administrators can provision accounts.
    # Operators may explicitly choose open/invite for public deployments.
    allow_registration: Literal["open", "invite", "closed"] = "closed"
    invite_code: str = ""
    # JWT signing secret. Leave empty for an ephemeral secret (tokens reset on
    # every restart) — set it in .env for stable tokens across restarts.
    jwt_secret: str = ""
    token_expire_minutes: int = Field(default=60 * 24 * 7, gt=0, le=60 * 24 * 365)

    # --- security ----------------------------------------------------------
    # TTL (seconds) of expiring signed URLs used to view private images.
    signed_url_ttl_seconds: int = Field(default=60 * 60 * 24, ge=60, le=7 * 86400)
    # In-process rate limits, per 60s window. See app/services/ratelimit.py.
    login_rate_limit_per_minute: int = Field(default=20, ge=0, le=1_000_000)  # per IP
    login_rate_limit_per_username: int = Field(default=5, ge=0, le=1_000_000)  # per account
    registration_rate_limit_per_minute: int = Field(default=10, ge=0, le=1_000_000)  # per IP
    registration_rate_limit_per_username: int = Field(default=3, ge=0, le=1_000_000)
    images_rate_limit_per_minute: int = Field(default=240, ge=0, le=1_000_000)  # per IP
    upload_rate_limit_per_minute: int = Field(default=60, ge=0, le=1_000_000)  # per user
    video_part_rate_limit_per_minute: int = Field(default=1000, ge=0, le=1_000_000)  # per user
    api_key_mutation_rate_limit_per_day: int = Field(default=100, ge=1, le=100_000)
    # Bound durable credentials per account. Rotation replaces one row and
    # therefore does not consume another slot.
    max_api_keys_per_user: int = Field(default=20, ge=1, le=1000)
    # Daily traffic aggregates older than this are deleted by the telemetry
    # writer at most once per UTC day. Keeps SQLite growth bounded.
    traffic_retention_days: int = Field(default=365, ge=1, le=3650)

    @model_validator(mode="after")
    def validate_video_chunk_size(self) -> "Settings":
        """A resumable part cannot be larger than the file accepted by the service."""
        if self.video_chunk_size_mb > self.max_video_size_mb:
            raise ValueError("video_chunk_size_mb must not exceed max_video_size_mb")
        if self.jwt_secret and len(self.jwt_secret.encode("utf-8")) < 32:
            raise ValueError("jwt_secret must be empty or contain at least 32 UTF-8 bytes")
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "oss.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def max_video_size_bytes(self) -> int:
        return self.max_video_size_mb * 1024 * 1024

    @property
    def video_chunk_size_bytes(self) -> int:
        return self.video_chunk_size_mb * 1024 * 1024

    @property
    def min_free_space_bytes(self) -> int:
        return self.min_free_space_mb * 1024 * 1024

    @property
    def user_storage_quota_bytes(self) -> int:
        return self.user_storage_quota_mb * 1024 * 1024

    @property
    def team_storage_quota_bytes(self) -> int:
        return self.team_storage_quota_mb * 1024 * 1024


settings = Settings()

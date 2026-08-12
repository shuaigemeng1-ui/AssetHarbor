"""Application settings, read from environment variables (OSS_* prefix) or a .env file."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OSS_", env_file=".env", extra="ignore")

    app_name: str = "oss"
    version: str = "0.6.0"

    # --- storage -----------------------------------------------------------
    # Base directory for the SQLite database and uploaded files.
    data_dir: Path = Path("./data")

    # --- upload limits -----------------------------------------------------
    max_upload_size_mb: int = 10

    # Video uploads use a resumable, fixed-size chunk protocol.  The defaults
    # deliberately keep individual reverse-proxy requests small while still
    # allowing large source files to be stored without buffering them in RAM.
    max_video_size_mb: int = 2048
    video_chunk_size_mb: int = 8
    video_upload_ttl_hours: int = 24 * 7
    max_active_video_uploads: int = 3
    min_free_space_mb: int = 1024
    video_cleanup_interval_seconds: int = 60 * 60

    # SQLite lock wait used by both SQLAlchemy and the connection PRAGMA.
    sqlite_busy_timeout_ms: int = 5000

    # --- short codes -------------------------------------------------------
    # Length (in base62 characters) of the random code used in image URLs.
    short_code_length: int = 10

    # --- public URL --------------------------------------------------------
    # Base URL used to build the links returned by the API, e.g.
    # "https://img.example.com". Leave empty to derive it from each request.
    public_url: str = ""

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
    token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- security ----------------------------------------------------------
    # Default visibility for new uploads: public | private.
    # private by default — uploads are not openly accessible until you
    # explicitly share them (public) or issue a signed link.
    default_visibility: str = "private"
    # TTL (seconds) of expiring signed URLs used to view private images.
    signed_url_ttl_seconds: int = 60 * 60 * 24  # 24h
    # In-process rate limits, per 60s window. See app/services/ratelimit.py.
    login_rate_limit_per_minute: int = 20        # per IP
    login_rate_limit_per_username: int = 5       # per account
    registration_rate_limit_per_minute: int = 10  # per IP
    registration_rate_limit_per_username: int = 3
    images_rate_limit_per_minute: int = 240      # GET /i/{code} per IP
    upload_rate_limit_per_minute: int = 60       # per user

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


settings = Settings()

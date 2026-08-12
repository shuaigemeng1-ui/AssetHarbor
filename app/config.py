"""Application settings, read from environment variables (OSS_* prefix) or a .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OSS_", env_file=".env", extra="ignore")

    app_name: str = "oss"
    version: str = "0.3.0"

    # --- storage -----------------------------------------------------------
    # Base directory for the SQLite database and uploaded files.
    data_dir: Path = Path("./data")

    # --- upload limits -----------------------------------------------------
    max_upload_size_mb: int = 10

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
    allow_registration: str = "open"
    invite_code: str = ""
    # JWT signing secret. Leave empty for an ephemeral secret (tokens reset on
    # every restart) — set it in .env for stable tokens across restarts.
    jwt_secret: str = ""
    token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- security ----------------------------------------------------------
    # Default visibility for new uploads: public | private.
    default_visibility: str = "public"
    # TTL (seconds) of expiring signed URLs used to view private images.
    signed_url_ttl_seconds: int = 60 * 60 * 24  # 24h
    # In-process rate limits, per 60s window. See app/services/ratelimit.py.
    login_rate_limit_per_minute: int = 20        # per IP
    login_rate_limit_per_username: int = 5       # per account
    images_rate_limit_per_minute: int = 240      # GET /i/{code} per IP
    upload_rate_limit_per_minute: int = 60       # per user

    @property
    def db_path(self) -> Path:
        return self.data_dir / "oss.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


settings = Settings()

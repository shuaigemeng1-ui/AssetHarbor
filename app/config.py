"""Application settings, read from environment variables (OSS_* prefix) or a .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OSS_", env_file=".env", extra="ignore")

    app_name: str = "oss"
    version: str = "0.1.0"

    # --- storage -----------------------------------------------------------
    # Base directory for the SQLite database and uploaded files.
    data_dir: Path = Path("./data")

    # --- upload limits -----------------------------------------------------
    max_upload_size_mb: int = 10

    # --- short codes -------------------------------------------------------
    # Length (in base62 characters) of the random code used in image URLs.
    short_code_length: int = 10

    # --- public URL --------------------------------------------------------
    # Base URL used to build the links returned by the upload API, e.g.
    # "https://img.example.com". Leave empty to derive it from each request.
    public_url: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "oss.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


settings = Settings()

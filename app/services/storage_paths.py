"""Canonical path validation for persisted media metadata."""

from pathlib import Path

from ..core.config import settings


def resolve_media_path(stored_path: str) -> Path:
    """Resolve a DB path and prove it remains inside the formal files root."""
    if not isinstance(stored_path, str) or not stored_path or "\x00" in stored_path:
        raise ValueError("invalid media storage path")
    relative = Path(stored_path)
    if relative.is_absolute():
        raise ValueError("absolute media storage path is forbidden")
    files_root = settings.files_dir.resolve()
    candidate = (settings.data_dir / relative).resolve()
    if not candidate.is_relative_to(files_root):
        raise ValueError("media storage path escapes files directory")
    return candidate

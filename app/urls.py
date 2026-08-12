"""URL building helpers."""

from fastapi import Request

from .config import settings


def build_image_url(request: Request, code: str) -> str:
    """Return the absolute public URL for an image short code.

    Uses ``OSS_PUBLIC_URL`` when configured (e.g. behind a reverse proxy),
    otherwise derives the base from the incoming request.
    """
    if settings.public_url:
        base = settings.public_url.rstrip("/")
    else:
        base = str(request.base_url).rstrip("/")
    return f"{base}/i/{code}"

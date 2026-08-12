"""URL building + signed (expiring) URL helpers.

Signed URLs let private images be viewed by anyone holding a *fresh, valid*
link (e.g. an <img> tag cannot send an Authorization header). Each link is
HMAC-SHA256 over ``{code}:{expires}``, bound to one image and one expiry
timestamp — guessing, tampering or replaying a signature fails verification.
"""

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Request

from ..core.config import settings

# HMAC key derived from the JWT secret (or ephemeral). With OSS_JWT_SECRET
# configured, signed links survive restarts.
_URL_SIGN_SECRET = settings.jwt_secret or secrets.token_urlsafe(48)


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


def _signature(code: str, expires: int, version: int) -> str:
    """16-byte HMAC-SHA256, base64url (128-bit security, short URLs).

    ``version`` is the image's signing version — bumping it invalidates every
    previously issued signed link for that image.
    """
    msg = f"{code}:{expires}:{version}".encode("utf-8")
    digest = hmac.new(_URL_SIGN_SECRET.encode("utf-8"), msg, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def sign_image_url(
    code: str, ttl_seconds: int | None = None, version: int = 1
) -> tuple[str, int]:
    """Return ``(signed_path, expires_unix_ts)`` for an expiring image link.

    Example path: ``/i/Ab3xYz9Kq1?expires=1767...&sig=xxxx``
    """
    ttl = ttl_seconds or settings.signed_url_ttl_seconds
    expires = int(time.time()) + ttl
    return f"/i/{code}?expires={expires}&sig={_signature(code, expires, version)}", expires


def build_signed_image_url(
    request: Request, code: str, ttl_seconds: int | None = None, version: int = 1
) -> tuple[str, int]:
    """Return ``(absolute_signed_url, expires_unix_ts)``."""
    signed_path, expires = sign_image_url(code, ttl_seconds, version)
    if settings.public_url:
        base = settings.public_url.rstrip("/")
    else:
        base = str(request.base_url).rstrip("/")
    return f"{base}{signed_path}", expires


def verify_image_signature(code: str, expires: str, sig: str, version: int = 1) -> bool:
    """Constant-time check: signature valid AND not expired AND for this code."""
    try:
        expires_ts = int(expires)
    except (TypeError, ValueError):
        return False
    if time.time() > expires_ts:
        return False
    expected = _signature(code, expires_ts, version)
    return hmac.compare_digest(expected, sig)

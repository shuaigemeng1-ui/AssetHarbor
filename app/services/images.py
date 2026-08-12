"""Core image handling: type sniffing, size limits and upload orchestration."""

import hashlib
import os
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Image
from .shortcode import generate_short_code

# ---------------------------------------------------------------------------
# Content sniffing — never trust user filenames or claimed MIME types.
# ---------------------------------------------------------------------------

# (magic bytes prefix, MIME type, file extension)
SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
    (b"RIFF", "image/webp", "webp"),  # RIFF....WEBP, verified below
    (b"BM", "image/bmp", "bmp"),
    (b"\x00\x00\x01\x00", "image/x-icon", "ico"),
    (b"II*\x00", "image/tiff", "tiff"),
    (b"MM\x00*", "image/tiff", "tiff"),
]

# XML prolog optional, then <svg
_SVG_RE = re.compile(rb"^\s*(?:<\?xml[^>]*>\s*)?<svg", re.IGNORECASE)

# ISO-BMFF brands for AVIF / HEIC
_FTYP_BRANDS = {
    b"avif": ("image/avif", "avif"),
    b"avis": ("image/avif", "avif"),
    b"heic": ("image/heic", "heic"),
    b"heix": ("image/heic", "heic"),
    b"mif1": ("image/heic", "heic"),
}

_SUPPORTED = ", ".join(sorted({mime for _, mime, _ in SIGNATURES} | {"image/svg+xml", "image/avif", "image/heic"}))


def detect_content_type(data: bytes) -> tuple[str, str] | None:
    """Sniff the real file type from magic bytes.

    Returns ``(mime_type, extension)`` or ``None`` when the payload is not a
    supported image.
    """
    if len(data) < 12:
        return None

    for magic, mime, ext in SIGNATURES:
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime, ext

    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in _FTYP_BRANDS:
            return _FTYP_BRANDS[brand]

    if _SVG_RE.match(data):
        return "image/svg+xml", "svg"

    return None


# ---------------------------------------------------------------------------
# Upload pipeline
# ---------------------------------------------------------------------------


async def _read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read the whole upload, aborting with 413 once the limit is exceeded."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"file exceeds the {settings.max_upload_size_mb} MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _unique_code(db: Session) -> str:
    """Generate a short code that does not collide with an existing image."""
    for _ in range(16):
        code = generate_short_code(settings.short_code_length)
        exists = db.execute(select(Image.id).where(Image.code == code)).scalar_one_or_none()
        if exists is None:
            return code
    raise RuntimeError("could not allocate a unique short code")


def _stored_path(code: str, ext: str) -> Path:
    """Shard two levels deep so one directory never holds too many files."""
    return Path("files") / code[:2] / code[2:4] / f"{code}.{ext}"


async def store_upload(file: UploadFile, db: Session) -> Image:
    """Validate, persist and index one uploaded image."""
    data = await _read_with_limit(file, settings.max_upload_size_mb * 1024 * 1024)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")

    detected = detect_content_type(data)
    if detected is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"unsupported file type; supported: {_SUPPORTED}",
        )

    mime, ext = detected
    digest = hashlib.sha256(data).hexdigest()
    code = _unique_code(db)

    rel_path = _stored_path(code, ext)
    abs_path = settings.data_dir / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file then rename, so a crash mid-write never leaves a
    # half-written image behind.
    tmp_path = abs_path.with_suffix(".tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, abs_path)

    image = Image(
        code=code,
        original_filename=file.filename or abs_path.name,
        stored_path=str(rel_path),
        content_type=mime,
        size=len(data),
        sha256=digest,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image

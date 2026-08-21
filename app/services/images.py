"""Core image handling: type sniffing, size limits and upload orchestration."""

import asyncio
import hashlib
import errno
import os
import re
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.auth_scope import has_global_admin_scope
from ..models import Image, User
from .library import (
    delete_group_items_for_media,
    fresh_library_user,
    library_lifecycle_lease,
    serialized_library_lifecycle,
    validate_team_scope,
)
from .shortcode import generate_short_code
from .storage_quota import enforce_storage_quota
from .storage_paths import resolve_media_path
from .teams import get_membership
from .videos import reserve_write_space

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
    (b"%PDF", "application/pdf", "pdf"),
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
_STORAGE_FULL_ERRNOS = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


def _is_storage_full_error(exc: BaseException) -> bool:
    """Recognize filesystem and SQLite disk/quota exhaustion errors."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "errno", None) in _STORAGE_FULL_ERRNOS:
            return True
        message = str(current).lower()
        if "database or disk is full" in message or "disk quota exceeded" in message:
            return True
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return False


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Cleanup is compensating/best-effort and must never hide the original
        # write or database error.
        pass


def _raise_storage_error(exc: BaseException) -> None:
    if _is_storage_full_error(exc):
        raise HTTPException(status_code=507, detail="insufficient storage space") from exc
    raise exc


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

# Bytes kept from the head of the stream for magic-byte sniffing. Large enough
# for every supported signature plus realistic SVG XML prologs.
_SNIFF_BYTES = 4096


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


def _safe_filename(filename: str | None) -> str:
    """Store a bounded display basename instead of client path metadata."""
    cleaned = (filename or "image").replace("\\", "/").split("/")[-1]
    cleaned = cleaned.replace("\x00", "").strip()
    return cleaned[:255] or "image"


async def store_upload(
    file: UploadFile,
    db: Session,
    owner: User | None = None,
    name: str | None = None,
    visibility: str = "public",
    team_id: int | None = None,
) -> Image:
    """Validate, persist and index one uploaded image.

    The request body is streamed to a temporary file outside the global
    lifecycle lease: type sniffing, the size limit and the incremental SHA-256
    digest all run without holding the lock, and file writes go through a
    worker thread so a large upload cannot block the event loop. Only the
    final authorization, quota enforcement, atomic publication and the
    owner/team-scoped DB commit are serialized with user/member/team deletion.
    """
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    head = bytearray()
    tmp_path: Path | None = None
    out = None
    fd: int | None = None
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix=".img-", dir=settings.data_dir)
        tmp_path = Path(raw_path)
        out = os.fdopen(fd, "wb")
        fd = None  # ownership moved to the buffered writer
        try:
            while True:
                chunk = await file.read(256 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"file exceeds the {settings.max_upload_size_mb} MB limit",
                    )
                if len(head) < _SNIFF_BYTES:
                    head.extend(chunk[: _SNIFF_BYTES - len(head)])
                digest.update(chunk)
                await asyncio.to_thread(out.write, chunk)
        finally:
            out.close()
            out = None

        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")

        detected = detect_content_type(bytes(head))
        if detected is None:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"unsupported file type; supported: {_SUPPORTED}",
            )

        mime, ext = detected
        original_filename = _safe_filename(file.filename)

        with library_lifecycle_lease():
            db.rollback()
            if owner is not None:
                owner = fresh_library_user(db, owner)
            if team_id is not None:
                if owner is None:
                    raise HTTPException(status_code=401, detail="an owner is required for team media")
                validate_team_scope(db, team_id, owner)
            if owner is not None:
                enforce_storage_quota(
                    db,
                    owner_id=owner.id,
                    team_id=team_id,
                    additional_bytes=size,
                )

            code = _unique_code(db)
            rel_path = _stored_path(code, ext)
            abs_path = settings.data_dir / rel_path
            with reserve_write_space(size):
                # Publish with an atomic rename, so a crash mid-write never
                # leaves a half-written image behind.
                try:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(tmp_path, abs_path)
                    tmp_path = None
                except OSError as exc:
                    _raise_storage_error(exc)

                image = Image(
                    code=code,
                    original_filename=original_filename,
                    name=(name or original_filename)[:255],
                    stored_path=str(rel_path),
                    content_type=mime,
                    size=size,
                    sha256=digest.hexdigest(),
                    media_kind="image",
                    owner_id=owner.id if owner else None,
                    visibility=visibility,
                    team_id=team_id,
                )
                try:
                    db.add(image)
                    db.commit()
                except Exception as exc:
                    try:
                        db.rollback()
                    finally:
                        # The formal file has already been atomically published.
                        # Compensate even if rollback itself encounters a disk error.
                        _unlink_quietly(abs_path)
                    _raise_storage_error(exc)
            db.refresh(image)
            return image
    except OSError as exc:
        _raise_storage_error(exc)
    finally:
        if out is not None:
            try:
                out.close()
            except OSError:
                pass
        elif fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            _unlink_quietly(tmp_path)


@serialized_library_lifecycle
def delete_image(db: Session, image: Image, actor: User | None = None) -> None:
    """Remove an image row and its file from disk."""
    image_id = image.id
    db.rollback()
    current = db.get(Image, image_id)
    if current is None:
        return
    if actor is not None:
        actor = fresh_library_user(db, actor)
        if not can_manage_image(db, actor, current):
            raise HTTPException(status_code=403, detail="media management privileges required")
    try:
        path = resolve_media_path(current.stored_path)
    except ValueError:
        # Corrupt metadata must never turn deletion into an arbitrary unlink.
        path = None
    delete_group_items_for_media(db, current.id)
    db.delete(current)
    db.commit()
    try:
        if path is not None:
            path.unlink(missing_ok=True)
    except OSError:
        pass  # the DB row is the source of truth; orphan files can be swept later


def can_manage_image(db: Session, user: User, image: Image) -> bool:
    """Manage an image/video under the team-asset ownership invariant.

    - Global admins (JWT/internal) can manage anything.
    - Personal media (``team_id is None``) are managed by their uploader.
    - Team media are controlled by team membership: the uploader may manage
      their own upload while they remain a member, and team owners/admins may
      manage any asset in the team. ``owner_id`` alone never bypasses a
      revoked membership.
    """
    if has_global_admin_scope(user):
        return True
    if image.team_id is not None:
        member = get_membership(db, image.team_id, user.id)
        if member is None:
            return False
        if image.owner_id == user.id or member.role in ("owner", "admin"):
            return True
        return False
    return image.owner_id == user.id


@serialized_library_lifecycle
def update_media_metadata(
    db: Session,
    *,
    code: str,
    media_kind: str,
    actor: User,
    name: str | None = None,
    visibility: str | None = None,
) -> Image:
    """Freshly authorize and update one image/video under the lifecycle lease.

    Route-level ORM rows and membership checks may be stale by the time a
    request reaches its commit.  Reopening the transaction after entering the
    shared lease makes member removal, role changes and user/media deletion win
    deterministically when they committed first.
    """
    db.rollback()
    actor = fresh_library_user(db, actor)
    media = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == media_kind)
    ).scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail=f"{media_kind} not found")
    if not can_manage_image(db, actor, media):
        raise HTTPException(
            status_code=403,
            detail=f"you can only modify {media_kind}s you manage",
        )

    if visibility is not None:
        if visibility not in ("public", "private"):
            raise HTTPException(
                status_code=422,
                detail="visibility must be 'public' or 'private'",
            )
        was_private = media.visibility == "private"
        if visibility != media.visibility:
            media.visibility = visibility
            if visibility == "private" and not was_private:
                # Revoke every previously issued signed link for this asset.
                media.signing_version += 1
    if name is not None:
        media.name = name.strip() or media.name

    db.commit()
    db.refresh(media)
    return media

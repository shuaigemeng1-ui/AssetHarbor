"""Resumable video upload storage, validation, finalization and cleanup."""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import SessionLocal
from ..models import Image, Team, UploadPart, UploadSession, User
from .library import (
    delete_team_groups,
    fresh_library_user,
    library_lifecycle_lease,
    serialized_library_lifecycle,
)
from .shortcode import generate_short_code
from .storage_quota import RESERVED_UPLOAD_STATUSES, enforce_storage_quota
from .teams import get_membership

_CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAMPLE_SIZE = 1024 * 1024
_ACTIVE_STATUSES = ("active", "verifying", "finalizing")

_lock_guard = threading.Lock()
_upload_locks: dict[str, threading.RLock] = {}
_upload_lock_users: dict[str, int] = {}
_session_create_lock = threading.Lock()
_finalization_lock = threading.RLock()
# Bound inbound request bodies as well as writes.  The frontend uses the same
# global concurrency (3), but this server-side guard is required because API
# clients are not trusted to obey it.  A per-upload gate also prevents many
# duplicate PUTs from each allocating a full chunk-sized temporary file.
_inbound_part_slots = threading.BoundedSemaphore(settings.video_chunk_concurrency)
_inbound_gate_guard = threading.Lock()
_inbound_upload_gates: dict[str, threading.BoundedSemaphore] = {}
_inbound_gate_users: dict[str, int] = {}

# Account for the peak bytes promised to in-flight writes.  Checking only
# ``disk_usage().free`` is racy: several requests can all observe the same free
# space before any of them starts writing.
_disk_reservation_lock = threading.Lock()
_reserved_write_bytes = 0
_STORAGE_FULL_ERRNOS = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


def _is_storage_full_error(exc: BaseException) -> bool:
    """Recognize direct filesystem and wrapped SQLite capacity failures."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "errno", None) in _STORAGE_FULL_ERRNOS:
            return True
        if getattr(current, "winerror", None) == 112:
            return True
        message = str(current).lower()
        if "database or disk is full" in message or "disk quota exceeded" in message:
            return True
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return False


def _serialized(lock: threading.Lock):
    """Serialize short cross-upload critical sections in one worker."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with lock:
                return function(*args, **kwargs)
        return wrapped
    return decorate


def _serialized_upload_session(function):
    """Acquire one session's lock after outer library/finalization locks."""
    @wraps(function)
    def wrapped(db: Session, upload: UploadSession, *args, **kwargs):
        with _leased_upload_lock(upload.upload_id):
            return function(db, upload, *args, **kwargs)

    return wrapped


@contextmanager
def _leased_upload_lock(upload_id: str):
    """Serialize filesystem/DB transitions and reclaim the lock at zero users.

    The reference is registered before attempting to acquire the lock, so the
    zero-user transition proves that no holder or waiter can still reference
    it.  Identity checks prevent a late release from deleting a newer lock.
    """
    with _lock_guard:
        lock = _upload_locks.setdefault(upload_id, threading.RLock())
        _upload_lock_users[upload_id] = _upload_lock_users.get(upload_id, 0) + 1
    try:
        with lock:
            yield lock
    finally:
        with _lock_guard:
            if _upload_locks.get(upload_id) is lock:
                remaining = max(0, _upload_lock_users.get(upload_id, 1) - 1)
                if remaining:
                    _upload_lock_users[upload_id] = remaining
                else:
                    _upload_lock_users.pop(upload_id, None)
                    _upload_locks.pop(upload_id, None)


def _lease_inbound_upload_gate(upload_id: str) -> threading.BoundedSemaphore:
    """Return one stable gate and count this request before it starts waiting."""
    with _inbound_gate_guard:
        gate = _inbound_upload_gates.setdefault(upload_id, threading.BoundedSemaphore(1))
        _inbound_gate_users[upload_id] = _inbound_gate_users.get(upload_id, 0) + 1
        return gate


def _release_inbound_upload_gate(upload_id: str, gate: threading.BoundedSemaphore) -> None:
    """Release a request reference and reclaim the gate at zero users."""
    with _inbound_gate_guard:
        # Identity protects against deleting a newer gate if an old request is
        # finishing after its session was retired and fully reclaimed.
        if _inbound_upload_gates.get(upload_id) is not gate:
            return
        remaining = max(0, _inbound_gate_users.get(upload_id, 1) - 1)
        if remaining:
            _inbound_gate_users[upload_id] = remaining
            return
        _inbound_gate_users.pop(upload_id, None)
        _inbound_upload_gates.pop(upload_id, None)


async def _acquire_part_slot(semaphore: threading.BoundedSemaphore) -> None:
    """Acquire a thread-safe gate without ever blocking the ASGI event loop.

    Polling with a non-blocking acquire is cancellation-safe.  In contrast,
    cancelling ``asyncio.to_thread(semaphore.acquire)`` leaves its worker alive
    and can leak a slot when that worker eventually succeeds.
    """
    while not semaphore.acquire(blocking=False):
        await asyncio.sleep(0.02)


@contextmanager
def _leased_inbound_upload_gate_sync(upload_id: str):
    """Synchronously serialize destructive lifecycle work with inbound PUTs.

    This helper is only used by synchronous routes and cleanup workers.  The
    async PUT path uses ``_acquire_part_slot`` so a contended thread primitive
    never blocks the ASGI event loop.
    """
    gate = _lease_inbound_upload_gate(upload_id)
    acquired = False
    try:
        gate.acquire()
        acquired = True
        yield gate
    finally:
        if acquired:
            gate.release()
        _release_inbound_upload_gate(upload_id, gate)


def _now() -> datetime:
    # SQLAlchemy's SQLite DATETIME adapter returns naive values.  Store UTC as
    # naive consistently so expiry comparisons work on every supported Python.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_expiry() -> datetime:
    return _now() + timedelta(hours=settings.video_upload_ttl_hours)


def session_dir(upload_id: str) -> Path:
    return settings.uploads_dir / upload_id


def session_file(upload_id: str) -> Path:
    return session_dir(upload_id) / "video.part"


def ensure_free_space(required_bytes: int = 0) -> None:
    """Reject writes that would cross the configured free-space reserve."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _disk_reservation_lock:
        free = shutil.disk_usage(settings.data_dir).free
        if free - _reserved_write_bytes - max(0, required_bytes) < settings.min_free_space_bytes:
            raise HTTPException(status_code=507, detail="insufficient storage space")


def _reserve_write_space(required_bytes: int) -> None:
    """Atomically reserve peak disk growth for one in-flight chunk request."""
    global _reserved_write_bytes
    required = max(0, required_bytes)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _disk_reservation_lock:
        free = shutil.disk_usage(settings.data_dir).free
        if free - _reserved_write_bytes - required < settings.min_free_space_bytes:
            raise HTTPException(status_code=507, detail="insufficient storage space")
        _reserved_write_bytes += required


def _release_write_space(reserved_bytes: int) -> None:
    global _reserved_write_bytes
    with _disk_reservation_lock:
        _reserved_write_bytes = max(0, _reserved_write_bytes - max(0, reserved_bytes))


@contextmanager
def reserve_write_space(required_bytes: int):
    """Share the video-chunk disk reservation with other media writers."""
    required = max(0, required_bytes)
    _reserve_write_space(required)
    try:
        yield
    finally:
        _release_write_space(required)


def _part_peak_growth(expected_size: int, offset: int, current_file_size: int) -> int:
    """Conservatively reserve temporary and random-access target allocation.

    Logical ``st_size`` is not allocated bytes for a sparse file.  Filling a
    hole may therefore consume a full chunk even when the logical file does
    not grow.  Reserve one temporary chunk plus at least one target chunk (or
    the larger logical extension) so the configured disk reserve is kept.
    """
    target_growth = max(0, offset + expected_size - current_file_size)
    return expected_size + max(expected_size, target_growth)


# ---------------------------------------------------------------------------
# Container sniffing -- extensions and request Content-Type are never trusted.
# ---------------------------------------------------------------------------

_ASF_MAGIC = bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c")
_BMFF_VIDEO_BRANDS = {
    b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"iso7", b"iso8", b"iso9",
    b"mp41", b"mp42", b"avc1", b"dash", b"MSNV", b"F4V ", b"M4VP",
}
_BMFF_M4V_BRANDS = {b"M4V ", b"M4VH", b"M4VP"}


def _bmff_brands(data: bytes) -> list[bytes]:
    """Return brands from the first well-formed ISO-BMFF ``ftyp`` box."""
    offset = 0
    limit = min(len(data), 64 * 1024)
    while offset + 8 <= limit:
        box_size = int.from_bytes(data[offset : offset + 4], "big")
        box_type = data[offset + 4 : offset + 8]
        header = 8
        if box_size == 1 and offset + 16 <= limit:
            box_size = int.from_bytes(data[offset + 8 : offset + 16], "big")
            header = 16
        if box_size < header or offset + box_size > limit:
            return []
        if box_type == b"ftyp" and box_size >= header + 8:
            payload = data[offset + header : offset + box_size]
            return [payload[:4], *[payload[i : i + 4] for i in range(8, len(payload) - 3, 4)]]
        offset += box_size
    return []


def detect_video_type(data: bytes) -> tuple[str, str] | None:
    """Return ``(MIME, extension)`` for a supported video container."""
    if len(data) < 4:
        return None

    brands = _bmff_brands(data)
    if brands:
        major = brands[0]
        if major.startswith((b"3g", b"3G")):
            return "video/3gpp", "3gp"
        if major == b"qt  ":
            return "video/quicktime", "mov"
        if major in _BMFF_M4V_BRANDS:
            return "video/x-m4v", "m4v"
        # HEIF/AVIF and M4A are explicitly not videos even if a compatible
        # brand happens to resemble a common BMFF brand.
        if major in {b"avif", b"avis", b"heic", b"heix", b"mif1", b"msf1", b"M4A "}:
            return None
        if any(brand in _BMFF_VIDEO_BRANDS or brand.startswith(b"mp4") for brand in brands):
            return "video/mp4", "mp4"

    if data.startswith(b"\x1a\x45\xdf\xa3"):
        header = data[: 64 * 1024].lower()
        if b"webm" in header:
            return "video/webm", "webm"
        if b"matroska" in header:
            return "video/x-matroska", "mkv"

    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "video/x-msvideo", "avi"
    if data.startswith((b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3")):
        return "video/mpeg", "mpg"
    # MPEG-TS uses fixed 188-byte packets.  Require at least two sync bytes;
    # accepting a single leading 0x47 makes any tiny ``G...`` payload pass.
    if len(data) >= 189 and data[0] == 0x47 and data[188] == 0x47:
        return "video/mp2t", "ts"
    if data.startswith(b"OggS") and b"theora" in data[: 64 * 1024].lower():
        return "video/ogg", "ogv"
    if data.startswith(b"FLV") and len(data) >= 5 and data[4] & 0x01:
        return "video/x-flv", "flv"
    if data.startswith(_ASF_MAGIC):
        return "video/x-ms-wmv", "wmv"
    return None


def supported_video_types() -> str:
    return "MP4/M4V, MOV, WebM, MKV, AVI, MPEG/MPG, TS, OGV, 3GP, FLV, WMV"


_VIDEO_EXTENSION_BY_CONTENT_TYPE = {
    "video/3gpp": "3gp",
    "video/quicktime": "mov",
    "video/x-m4v": "m4v",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/x-msvideo": "avi",
    "video/mpeg": "mpg",
    "video/mp2t": "ts",
    "video/ogg": "ogv",
    "video/x-flv": "flv",
    "video/x-ms-wmv": "wmv",
}


# ---------------------------------------------------------------------------
# Fingerprints and session lifecycle
# ---------------------------------------------------------------------------

def calculate_quick_fingerprint(path: Path, size: int) -> str:
    """Match the browser's size + head/middle/tail 1 MiB fingerprint."""
    offsets = (0, max(0, size // 2 - _SAMPLE_SIZE // 2), max(0, size - _SAMPLE_SIZE))
    hashes: list[str] = []
    with path.open("rb") as file:
        for offset in offsets:
            file.seek(offset)
            hashes.append(hashlib.sha256(file.read(min(_SAMPLE_SIZE, size - offset))).hexdigest())
    value = f"{size}:{hashes[0]}:{hashes[1]}:{hashes[2]}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/").split("/")[-1].replace("\x00", "").strip()
    return cleaned[:255] or "video"


def _check_team_access(db: Session, team_id: int | None, user: User) -> None:
    if team_id is None:
        return
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    if user.role != "admin" and get_membership(db, team_id, user.id) is None:
        raise HTTPException(status_code=403, detail="you are not a member of this team")


@serialized_library_lifecycle
@_serialized(_session_create_lock)
def create_upload_session(
    db: Session,
    user: User,
    *,
    filename: str,
    size: int,
    name: str,
    visibility: str,
    team_id: int | None,
    fingerprint: str,
) -> UploadSession:
    # The create lock is also held by team dissolution and orphan cleanup.
    # Refresh the transaction after entering it so a team checked by the route
    # cannot be deleted while this session is being inserted.
    db.rollback()
    user = fresh_library_user(db, user)
    if visibility not in ("public", "private"):
        raise HTTPException(status_code=422, detail="visibility must be 'public' or 'private'")
    if size <= 0:
        raise HTTPException(status_code=422, detail="size must be greater than zero")
    if size > settings.max_video_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"video exceeds the {settings.max_video_size_mb} MB limit",
        )
    normalized_fp = fingerprint.lower()
    if not _SHA256_RE.fullmatch(normalized_fp):
        raise HTTPException(status_code=422, detail="fingerprint must be a SHA-256 hex digest")
    _check_team_access(db, team_id, user)

    # These values become immutable metadata on the finalized asset. Session
    # reuse must therefore match the complete normalized intent, not merely
    # the file bytes. In particular, a public initialization must never be
    # silently resumed when the caller asks for a private upload later.
    normalized_filename = _safe_filename(filename)
    normalized_name = name.strip()[:255] or normalized_filename

    now = _now()
    existing = db.execute(
        select(UploadSession)
        .where(
            UploadSession.owner_id == user.id,
            UploadSession.fingerprint == normalized_fp,
            UploadSession.size == size,
            UploadSession.original_filename == normalized_filename,
            UploadSession.name == normalized_name,
            UploadSession.visibility == visibility,
            UploadSession.team_id.is_(team_id) if team_id is None else UploadSession.team_id == team_id,
            UploadSession.status.in_(_ACTIVE_STATUSES),
            UploadSession.expires_at > now,
        )
        .order_by(UploadSession.created_at.desc())
    ).scalars().first()
    if existing is not None:
        return existing

    # A new session reserves its declared bytes. Existing idempotent sessions
    # returned above already hold that reservation and must not be double-counted.
    enforce_storage_quota(
        db,
        owner_id=user.id,
        team_id=team_id,
        additional_bytes=size,
    )

    active_count = db.scalar(
        select(func.count()).select_from(UploadSession).where(
            UploadSession.owner_id == user.id,
            UploadSession.status.in_(RESERVED_UPLOAD_STATUSES),
            UploadSession.expires_at > now,
        )
    ) or 0
    if active_count >= settings.max_active_video_uploads:
        raise HTTPException(
            status_code=429,
            detail=f"at most {settings.max_active_video_uploads} unfinished video uploads are allowed",
        )

    # Reserve enough free capacity for the source; this is a conservative
    # admission check, repeated per chunk because other uploads may consume it.
    ensure_free_space(size)
    chunk_size = settings.video_chunk_size_bytes
    if chunk_size <= 0:
        raise RuntimeError("video chunk size must be positive")
    upload = UploadSession(
        upload_id=str(uuid.uuid4()),
        owner_id=user.id,
        team_id=team_id,
        original_filename=normalized_filename,
        name=normalized_name,
        visibility=visibility,
        size=size,
        chunk_size=chunk_size,
        total_parts=math.ceil(size / chunk_size),
        fingerprint=normalized_fp,
        status="active",
        expires_at=_new_expiry(),
        resume_info="",
        created_at=now,
        updated_at=now,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    session_dir(upload.upload_id).mkdir(parents=True, exist_ok=True)
    return upload


def get_upload_for_user(
    db: Session,
    upload_id: str,
    user: User,
    *,
    cleanup_expired: bool = True,
) -> UploadSession:
    upload = db.get(UploadSession, upload_id)
    if upload is None or (upload.owner_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="upload session not found")
    if upload.expires_at <= _now() and upload.status == "finalizing":
        recover_finalizing_session(db, upload)
        db.expire_all()
        upload = db.get(UploadSession, upload_id)
        if upload is not None and upload.expires_at > _now():
            return upload
    if upload is not None and upload.expires_at <= _now():
        # The PUT endpoint disables inline cleanup: it is async, while the
        # synchronous cancellation gate may legitimately wait for an earlier
        # inbound request.  Hourly cleanup removes that expired session.
        if cleanup_expired:
            cancel_upload_session(db, upload, user)
        raise HTTPException(status_code=410, detail="upload session expired")
    if upload is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    return upload


def uploaded_part_numbers(db: Session, upload_id: str) -> list[int]:
    return list(
        db.execute(
            select(UploadPart.part_number)
            .where(UploadPart.upload_id == upload_id)
            .order_by(UploadPart.part_number)
        ).scalars().all()
    )


def _expected_part(upload: UploadSession, part_number: int) -> tuple[int, int]:
    if part_number < 0 or part_number >= upload.total_parts:
        raise HTTPException(status_code=416, detail="part number outside upload range")
    offset = part_number * upload.chunk_size
    return offset, min(upload.chunk_size, upload.size - offset)


def _parse_content_range(value: str | None, upload: UploadSession, part_number: int) -> tuple[int, int]:
    if not value:
        raise HTTPException(status_code=400, detail="Content-Range header is required")
    match = _CONTENT_RANGE_RE.fullmatch(value.strip())
    if not match:
        raise HTTPException(status_code=400, detail="invalid Content-Range header")
    try:
        start, end, total = map(int, match.groups())
    except (ValueError, OverflowError) as exc:
        # Python rejects extremely long integer strings; expose a stable client
        # error instead of leaking that conversion failure as a 500 response.
        raise HTTPException(status_code=400, detail="invalid Content-Range header") from exc
    expected_start, expected_size = _expected_part(upload, part_number)
    if total != upload.size or start != expected_start or end != start + expected_size - 1:
        raise HTTPException(status_code=416, detail="Content-Range does not match this part")
    return expected_start, expected_size


async def store_upload_part(
    db: Session,
    upload: UploadSession,
    user: User,
    part_number: int,
    request: Request,
    content_range: str | None,
    expected_sha256: str | None,
) -> UploadPart:
    upload_id = upload.upload_id
    if upload.status not in ("active", "finalizing", "completed"):
        raise HTTPException(status_code=409, detail=f"upload cannot accept parts while {upload.status}")

    offset, expected_size = _parse_content_range(content_range, upload, part_number)
    digest_header = (expected_sha256 or "").lower()
    if not _SHA256_RE.fullmatch(digest_header):
        raise HTTPException(status_code=400, detail="X-Chunk-SHA256 header is required")
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) != expected_size:
                raise HTTPException(status_code=400, detail="Content-Length does not match this part")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Content-Length") from exc

    global_slot_acquired = False
    upload_gate = _lease_inbound_upload_gate(upload_id)
    upload_gate_reference_held = True
    upload_gate_acquired = False
    reserved_bytes = 0
    tmp_path: Path | None = None
    try:
        # Serialize one upload before consuming scarce global capacity.  If the
        # order is reversed, duplicate PUTs for one upload can occupy all three
        # global slots while merely waiting for this per-upload gate.
        await _acquire_part_slot(upload_gate)
        upload_gate_acquired = True
        await _acquire_part_slot(_inbound_part_slots)
        global_slot_acquired = True

        # Authentication happens before this gate.  A DELETE may therefore
        # retire the session while an already-authorized PUT is waiting.  End
        # the earlier read transaction and revalidate before creating any
        # directory or temporary file, so that stale PUT cannot resurrect
        # canceled storage.
        db.rollback()
        user = fresh_library_user(db, user)
        gated_upload = _fresh_upload_session(db, upload_id)
        if gated_upload is None:
            raise HTTPException(status_code=404, detail="upload session not found")
        if gated_upload.owner_id != user.id and user.role != "admin":
            raise HTTPException(status_code=404, detail="upload session not found")
        _check_team_access(db, gated_upload.team_id, user)
        if gated_upload.expires_at <= _now():
            raise HTTPException(status_code=410, detail="upload session expired")
        if gated_upload.status not in ("active", "finalizing", "completed"):
            raise HTTPException(
                status_code=409,
                detail=f"upload cannot accept parts while {gated_upload.status}",
            )

        part_path = session_file(upload_id)
        current_file_size = part_path.stat().st_size if part_path.is_file() else 0
        peak_growth = _part_peak_growth(expected_size, offset, current_file_size)
        _reserve_write_space(peak_growth)
        reserved_bytes = peak_growth

        directory = session_dir(upload_id)
        directory.mkdir(parents=True, exist_ok=True)
        tmp_path = directory / f"part-{part_number}-{uuid.uuid4().hex}.tmp"
        digest = hashlib.sha256()
        received = 0
        with tmp_path.open("xb") as tmp:
            async for chunk in request.stream():
                if not chunk:
                    continue
                received += len(chunk)
                if received > expected_size:
                    raise HTTPException(status_code=413, detail="chunk exceeds its declared range")
                digest.update(chunk)
                tmp.write(chunk)
            tmp.flush()
            os.fsync(tmp.fileno())
        if received != expected_size:
            raise HTTPException(status_code=400, detail="chunk length does not match Content-Range")
        actual_sha = digest.hexdigest()
        if actual_sha != digest_header:
            raise HTTPException(status_code=409, detail="chunk SHA-256 mismatch")

        # Do not acquire the library lease while holding the inbound gate:
        # cancellation uses library -> inbound, so the reverse order would
        # deadlock. Release body-stream capacity first, then run the short
        # final commit in a worker with the canonical lock order. A cancel may
        # win in between; the fresh session/actor checks then return 404/401
        # without registering bytes or recreating the directory.
        _inbound_part_slots.release()
        global_slot_acquired = False
        upload_gate.release()
        upload_gate_acquired = False
        _release_inbound_upload_gate(upload_id, upload_gate)
        upload_gate_reference_held = False
        return await asyncio.to_thread(
            _commit_upload_part,
            upload_id,
            user,
            part_number,
            offset,
            received,
            actual_sha,
            tmp_path,
        )
    except OSError as exc:
        if _is_storage_full_error(exc):
            raise HTTPException(status_code=507, detail="insufficient storage space") from exc
        raise
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if reserved_bytes:
            _release_write_space(reserved_bytes)
        # Release in reverse acquisition order, then drop this request's gate
        # reference.  Destructive operations wait on this gate before deleting
        # database rows or the upload directory.
        if global_slot_acquired:
            _inbound_part_slots.release()
        if upload_gate_acquired:
            upload_gate.release()
        if upload_gate_reference_held:
            _release_inbound_upload_gate(upload_id, upload_gate)


def _commit_upload_part(
    upload_id: str,
    user: User,
    part_number: int,
    offset: int,
    received: int,
    actual_sha: str,
    tmp_path: Path,
) -> UploadPart:
    """Fresh-authorize and publish one staged part under canonical locks."""
    with library_lifecycle_lease():
        with _leased_inbound_upload_gate_sync(upload_id):
            with _leased_upload_lock(upload_id):
                with SessionLocal() as commit_db:
                    commit_db.rollback()
                    user = fresh_library_user(commit_db, user)
                    current = _fresh_upload_session(commit_db, upload_id)
                    if current is None:
                        raise HTTPException(status_code=404, detail="upload session not found")
                    if current.owner_id != user.id and user.role != "admin":
                        raise HTTPException(status_code=404, detail="upload session not found")
                    _check_team_access(commit_db, current.team_id, user)

                    existing = commit_db.execute(select(UploadPart).where(
                        UploadPart.upload_id == upload_id,
                        UploadPart.part_number == part_number,
                    )).scalar_one_or_none()
                    if existing is not None:
                        if existing.sha256 == actual_sha and existing.size == received:
                            if current.status == "active":
                                current.expires_at = _new_expiry()
                                current.updated_at = _now()
                                commit_db.commit()
                            return existing
                        raise HTTPException(
                            status_code=409,
                            detail="part number already contains different data",
                        )
                    if current.status != "active":
                        raise HTTPException(
                            status_code=409,
                            detail=f"upload cannot accept parts while {current.status}",
                        )
                    if not tmp_path.is_file():
                        raise HTTPException(status_code=409, detail="chunk staging data is missing")

                    if part_number == 0:
                        with tmp_path.open("rb") as first:
                            detected = detect_video_type(
                                first.read(min(received, 64 * 1024))
                            )
                        if detected is None:
                            raise HTTPException(
                                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                                detail=(
                                    "unsupported video type; supported: "
                                    f"{supported_video_types()}"
                                ),
                            )

                    part_path = session_file(upload_id)
                    mode = "r+b" if part_path.exists() else "w+b"
                    with part_path.open(mode) as target, tmp_path.open("rb") as source:
                        target.seek(offset)
                        while True:
                            block = source.read(256 * 1024)
                            if not block:
                                break
                            target.write(block)
                        target.flush()
                        os.fsync(target.fileno())

                    record = UploadPart(
                        upload_id=upload_id,
                        part_number=part_number,
                        offset=offset,
                        size=received,
                        sha256=actual_sha,
                        created_at=_now(),
                    )
                    current.expires_at = _new_expiry()
                    current.updated_at = _now()
                    commit_db.add(record)
                    try:
                        commit_db.commit()
                    except IntegrityError:
                        commit_db.rollback()
                        duplicate = commit_db.execute(select(UploadPart).where(
                            UploadPart.upload_id == upload_id,
                            UploadPart.part_number == part_number,
                        )).scalar_one_or_none()
                        if (
                            duplicate
                            and duplicate.sha256 == actual_sha
                            and duplicate.size == received
                        ):
                            return duplicate
                        raise HTTPException(
                            status_code=409,
                            detail="part number already contains different data",
                        )
                    commit_db.refresh(record)
                    return record


def _verify_parts_and_sha256(path: Path, parts: list[UploadPart]) -> str:
    """Re-hash every stored chunk while calculating the full-file digest."""
    whole = hashlib.sha256()
    with path.open("rb") as file:
        for part in parts:
            file.seek(part.offset)
            remaining = part.size
            chunk_digest = hashlib.sha256()
            while remaining:
                block = file.read(min(1024 * 1024, remaining))
                if not block:
                    raise HTTPException(status_code=409, detail="uploaded video data is incomplete")
                remaining -= len(block)
                chunk_digest.update(block)
                whole.update(block)
            if chunk_digest.hexdigest() != part.sha256:
                raise HTTPException(status_code=409, detail=f"stored part {part.part_number} failed integrity check")
    return whole.hexdigest()


def _unique_video_code(db: Session) -> str:
    for _ in range(16):
        code = generate_short_code(settings.short_code_length)
        if db.execute(select(Image.id).where(Image.code == code)).scalar_one_or_none() is None:
            return code
    raise RuntimeError("could not allocate a unique short code")


def _create_final_image(db: Session, upload: UploadSession, info: dict[str, str]) -> Image:
    existing = db.execute(select(Image).where(Image.code == info["code"])).scalar_one_or_none()
    if existing is not None:
        return existing
    image = Image(
        code=info["code"],
        original_filename=upload.original_filename,
        name=upload.name,
        visibility=upload.visibility,
        stored_path=info["stored_path"],
        content_type=info["content_type"],
        size=upload.size,
        sha256=info["sha256"],
        media_kind="video",
        owner_id=upload.owner_id,
        team_id=upload.team_id,
    )
    db.add(image)
    db.flush()
    return image


def complete_upload_session(db: Session, upload: UploadSession, user: User) -> Image:
    """Verify outside the global lifecycle lease, then fresh-authorize commit.

    Lock order is always library -> finalization -> upload.  Phase one records
    a unique verification lease while holding that order.  The expensive
    multi-gigabyte read then runs without any process-global lock.  Phase two
    reacquires the same order and only publishes bytes after revalidating the
    user, team membership and verification nonce from a fresh transaction.
    """
    upload_id = upload.upload_id
    nonce = uuid.uuid4().hex
    with library_lifecycle_lease():
        with _finalization_lock:
            with _leased_upload_lock(upload_id):
                # End the authorization/status read transaction. Team
                # dissolution and user/member deletion commit under the same
                # outer lifecycle lease, so this snapshot cannot be stale.
                db.rollback()
                user = fresh_library_user(db, user)
                current = db.get(UploadSession, upload_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                if current.owner_id != user.id and user.role != "admin":
                    raise HTTPException(status_code=404, detail="upload session not found")
                if current.status == "completed" and current.final_code:
                    image = db.execute(select(Image).where(
                        Image.code == current.final_code, Image.media_kind == "video"
                    )).scalar_one_or_none()
                    if image is not None:
                        return image
                    raise HTTPException(status_code=409, detail="completed video metadata is missing")
                if current.status == "finalizing":
                    recover_finalizing_session(db, current)
                    db.expire_all()
                    current = db.get(UploadSession, upload_id)
                    if current and current.status == "completed" and current.final_code:
                        return db.execute(
                            select(Image).where(Image.code == current.final_code)
                        ).scalar_one()
                    raise HTTPException(
                        status_code=409,
                        detail="upload finalization is incomplete; retry shortly",
                    )
                if current.status != "active":
                    raise HTTPException(
                        status_code=409,
                        detail=f"upload cannot be completed while {current.status}",
                    )
                _check_team_access(db, current.team_id, user)

                parts = db.execute(
                    select(UploadPart)
                    .where(UploadPart.upload_id == current.upload_id)
                    .order_by(UploadPart.part_number)
                ).scalars().all()
                if (
                    len(parts) != current.total_parts
                    or [part.part_number for part in parts]
                    != list(range(current.total_parts))
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="not all video parts have been uploaded",
                    )
                for part in parts:
                    expected_offset, expected_size = _expected_part(
                        current, part.part_number
                    )
                    if part.offset != expected_offset or part.size != expected_size:
                        raise HTTPException(
                            status_code=409,
                            detail="uploaded part metadata is inconsistent",
                        )

                source = session_file(current.upload_id)
                if not source.is_file() or source.stat().st_size != current.size:
                    raise HTTPException(
                        status_code=409,
                        detail="uploaded video data is incomplete",
                    )
                expected_size = current.size
                expected_fingerprint = current.fingerprint
                current.status = "verifying"
                current.resume_info = json.dumps(
                    {"verification_nonce": nonce}, ensure_ascii=False
                )
                current.updated_at = _now()
                current.expires_at = _new_expiry()
                db.commit()

    # No global lifecycle/finalization/upload lock is held while reading the
    # full source. Status=verifying prevents PUT from mutating it; cancellation
    # may still retire it, which the second phase detects before publication.
    try:
        with source.open("rb") as file:
            detected = detect_video_type(file.read(min(expected_size, 64 * 1024)))
        if detected is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"unsupported video type; supported: {supported_video_types()}",
            )
        if calculate_quick_fingerprint(source, expected_size) != expected_fingerprint:
            raise HTTPException(
                status_code=409,
                detail="video fingerprint does not match initialization",
            )
        digest = _verify_parts_and_sha256(source, parts)
    except FileNotFoundError as exc:
        _reset_verifying_upload(db, upload_id, nonce)
        raise HTTPException(status_code=404, detail="upload session not found") from exc
    except Exception:
        _reset_verifying_upload(db, upload_id, nonce)
        raise

    content_type, extension = detected
    with library_lifecycle_lease():
        with _finalization_lock:
            with _leased_upload_lock(upload_id):
                db.rollback()
                # Resolve the target session before refreshing the actor.  An
                # administrator may finalize another user's upload and then
                # be deleted while the unlocked hash is running.  In that
                # case the surviving upload must leave ``verifying`` before
                # the actor's original 401 is propagated.
                current = _fresh_upload_session(db, upload_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                try:
                    user = fresh_library_user(db, user)
                except HTTPException:
                    _return_verifying_to_active(db, current, nonce)
                    raise
                if current.owner_id != user.id and user.role != "admin":
                    _return_verifying_to_active(db, current, nonce)
                    raise HTTPException(status_code=404, detail="upload session not found")
                if not _has_verification_nonce(current, nonce):
                    raise HTTPException(
                        status_code=409,
                        detail=f"upload cannot be completed while {current.status}",
                    )
                try:
                    _check_team_access(db, current.team_id, user)
                except HTTPException:
                    _return_verifying_to_active(db, current, nonce)
                    raise
                source = session_file(current.upload_id)
                if not source.is_file() or source.stat().st_size != current.size:
                    _return_verifying_to_active(db, current, nonce)
                    raise HTTPException(
                        status_code=409,
                        detail="uploaded video data is incomplete",
                    )

                try:
                    code = _unique_video_code(db)
                    rel_path = (
                        Path("files")
                        / code[:2]
                        / code[2:4]
                        / f"{code}.{extension}"
                    )
                    destination = settings.data_dir / rel_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    info = {
                        "code": code,
                        "stored_path": str(rel_path),
                        "content_type": content_type,
                        "sha256": digest,
                    }

                    # Persist recovery metadata before the atomic move. On a
                    # crash, startup can finish from source or destination.
                    current.status = "finalizing"
                    current.resume_info = json.dumps(info, ensure_ascii=False)
                    current.updated_at = _now()
                    current.expires_at = _new_expiry()
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    failed = _fresh_upload_session(db, upload_id)
                    if failed is not None:
                        _return_verifying_to_active(db, failed, nonce)
                    if _is_storage_full_error(exc):
                        raise HTTPException(
                            status_code=507,
                            detail="insufficient storage space",
                        ) from exc
                    if isinstance(exc, OSError):
                        raise HTTPException(
                            status_code=500,
                            detail="could not prepare video storage",
                        ) from exc
                    raise

                try:
                    os.replace(source, destination)
                except OSError:
                    db.expire_all()
                    failed = db.get(UploadSession, current.upload_id)
                    if failed is not None and source.exists():
                        failed.status = "active"
                        failed.resume_info = ""
                        failed.updated_at = _now()
                        db.commit()
                    raise

                try:
                    db.expire_all()
                    final = db.get(UploadSession, current.upload_id)
                    if final is None:
                        raise RuntimeError(
                            "upload session disappeared during finalization"
                        )
                    image = _create_final_image(db, final, info)
                    final.status = "completed"
                    final.final_code = code
                    final.completed_at = _now()
                    final.updated_at = _now()
                    final.expires_at = _new_expiry()
                    db.commit()
                    db.refresh(image)
                    try:
                        session_dir(current.upload_id).rmdir()
                    except OSError:
                        pass
                    return image
                except Exception:
                    db.rollback()
                    # Keep durable finalizing state for startup/request retry.
                    raise


def _has_verification_nonce(upload: UploadSession, nonce: str) -> bool:
    if upload.status != "verifying":
        return False
    try:
        info = json.loads(upload.resume_info)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return info.get("verification_nonce") == nonce


def _fresh_upload_session(db: Session, upload_id: str) -> UploadSession | None:
    """Bypass an identity-map row that another request may have deleted."""
    return db.execute(
        select(UploadSession)
        .where(UploadSession.upload_id == upload_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _return_verifying_to_active(
    db: Session, upload: UploadSession, nonce: str
) -> bool:
    """Reset exactly the verification attempt represented by ``nonce``."""
    if not _has_verification_nonce(upload, nonce):
        return False
    upload.status = "active" if session_file(upload.upload_id).is_file() else "failed"
    upload.resume_info = ""
    upload.updated_at = _now()
    upload.expires_at = _new_expiry()
    db.commit()
    return True


def _reset_verifying_upload(db: Session, upload_id: str, nonce: str) -> None:
    """Best-effort failure compensation using the canonical lock order."""
    with library_lifecycle_lease():
        with _finalization_lock:
            with _leased_upload_lock(upload_id):
                db.rollback()
                current = _fresh_upload_session(db, upload_id)
                if current is not None:
                    _return_verifying_to_active(db, current, nonce)


def _validated_finalizing_info(
    raw_info: str,
) -> tuple[dict[str, str], Path]:
    """Parse recovery metadata and derive a destination without trusting it."""
    try:
        info = json.loads(raw_info)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid recovery metadata") from exc
    required = {"code", "stored_path", "content_type", "sha256"}
    if not isinstance(info, dict) or not required.issubset(info):
        raise ValueError("missing recovery fields")
    code = info["code"]
    content_type = info["content_type"]
    sha256 = info["sha256"]
    stored_path = info["stored_path"]
    if (
        not isinstance(code, str)
        or re.fullmatch(rf"[0-9A-Za-z]{{{settings.short_code_length}}}", code)
        is None
    ):
        raise ValueError("invalid recovery code")
    if not isinstance(sha256, str) or _SHA256_RE.fullmatch(sha256) is None:
        raise ValueError("invalid recovery digest")
    extension = _VIDEO_EXTENSION_BY_CONTENT_TYPE.get(content_type)
    if extension is None:
        raise ValueError("invalid recovery content type")
    expected_relative = Path("files") / code[:2] / code[2:4] / f"{code}.{extension}"
    if not isinstance(stored_path, str) or Path(stored_path) != expected_relative:
        raise ValueError("invalid recovery path")
    files_root = settings.files_dir.resolve()
    destination = (settings.data_dir / expected_relative).resolve()
    if not destination.is_relative_to(files_root):
        raise ValueError("recovery path escapes files directory")
    return {
        "code": code,
        "stored_path": str(expected_relative),
        "content_type": content_type,
        "sha256": sha256,
    }, destination


@serialized_library_lifecycle
@_serialized(_finalization_lock)
@_serialized_upload_session
def recover_finalizing_session(db: Session, upload: UploadSession) -> None:
    """Idempotently finish one session interrupted around its atomic move."""
    upload_id = upload.upload_id
    db.rollback()
    upload = db.get(UploadSession, upload_id)
    if upload is None:
        return
    if upload.status != "finalizing":
        return
    try:
        info, destination = _validated_finalizing_info(upload.resume_info)
    except ValueError:
        source = session_file(upload.upload_id)
        upload.status = "active" if source.is_file() else "failed"
        upload.resume_info = ""
        upload.updated_at = _now()
        upload.expires_at = _new_expiry()
        db.commit()
        return

    source = session_file(upload.upload_id)
    if not destination.is_file() and source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
    if not destination.is_file():
        upload.status = "failed"
        upload.updated_at = _now()
        upload.expires_at = _new_expiry()
        db.commit()
        return

    owner = db.get(User, upload.owner_id)
    try:
        if owner is None:
            raise HTTPException(status_code=404, detail="upload owner not found")
        _check_team_access(db, upload.team_id, owner)
    except HTTPException:
        # Authorization may have been revoked while the process was down.
        # Restore the atomically moved file to resumable storage and never
        # create an owner/team-scoped asset from stale authorization.
        if destination.is_file():
            if not source.is_file():
                session_dir(upload.upload_id).mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
            else:
                destination.unlink(missing_ok=True)
        upload.status = "active" if owner is not None else "failed"
        upload.resume_info = ""
        upload.updated_at = _now()
        upload.expires_at = _new_expiry()
        db.commit()
        return

    image = _create_final_image(db, upload, info)
    upload.status = "completed"
    upload.final_code = info["code"]
    upload.completed_at = upload.completed_at or _now()
    upload.updated_at = _now()
    upload.expires_at = _new_expiry()
    db.commit()
    db.refresh(image)


@serialized_library_lifecycle
@_serialized(_finalization_lock)
@_serialized_upload_session
def recover_verifying_session(db: Session, upload: UploadSession) -> None:
    """Return an interrupted pre-publication verification to a resumable state."""
    upload_id = upload.upload_id
    db.rollback()
    current = db.get(UploadSession, upload_id)
    if current is None or current.status != "verifying":
        return
    current.status = "active" if session_file(upload_id).is_file() else "failed"
    current.resume_info = ""
    current.updated_at = _now()
    current.expires_at = _new_expiry()
    db.commit()


def recover_finalizing_uploads() -> int:
    """Recover interrupted verification/finalization after initialization."""
    recovered = 0
    with SessionLocal() as db:
        uploads = db.execute(
            select(UploadSession).where(
                UploadSession.status.in_(("verifying", "finalizing"))
            )
        ).scalars().all()
        for upload in uploads:
            try:
                if upload.status == "verifying":
                    recover_verifying_session(db, upload)
                else:
                    recover_finalizing_session(db, upload)
                recovered += 1
            except OSError:
                db.rollback()
    return recovered


def _delete_upload_session_locked(db: Session, upload_id: str) -> None:
    """Delete tracking and temp bytes while lifecycle/inbound/upload are held."""
    current = _fresh_upload_session(db, upload_id)
    destination: Path | None = None
    if current is not None and current.status == "finalizing":
        try:
            _info, destination = _validated_finalizing_info(current.resume_info)
        except ValueError:
            # Corrupt recovery metadata is never interpreted as a filesystem
            # path. The upload directory remains safe to remove by upload_id.
            destination = None
    db.execute(delete(UploadPart).where(UploadPart.upload_id == upload_id))
    if current is not None:
        db.delete(current)
    db.commit()
    shutil.rmtree(session_dir(upload_id), ignore_errors=True)
    if destination is not None:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            # DB/session deletion remains the source of truth. Startup orphan
            # maintenance may retry a filesystem cleanup that the OS denied.
            pass


def cancel_upload_session(
    db: Session,
    upload: UploadSession,
    actor: User,
) -> None:
    """Cancel through a fresh owner/admin check under canonical locks."""
    upload_id = upload.upload_id
    # First drain a body that was already streaming, without holding the
    # lifecycle lease. This intentionally gives a concurrent role/membership
    # revocation a chance to commit while DELETE waits. The destructive phase
    # below then reacquires using the one canonical order.
    with _leased_inbound_upload_gate_sync(upload_id):
        pass

    # PUT releases its streaming gate before attempting this same
    # library -> inbound -> upload order, so there is no reverse-order wait.
    with library_lifecycle_lease():
        with _leased_inbound_upload_gate_sync(upload_id):
            with _leased_upload_lock(upload_id):
                db.rollback()
                current = _fresh_upload_session(db, upload_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="upload session not found")
                actor = fresh_library_user(db, actor)
                if current.owner_id != actor.id and actor.role != "admin":
                    raise HTTPException(status_code=404, detail="upload session not found")
                _delete_upload_session_locked(db, upload_id)


def cancel_upload_session_internal(db: Session, upload: UploadSession) -> None:
    """Trusted lifecycle cleanup for expiry and explicit owner deletion."""
    upload_id = upload.upload_id
    with library_lifecycle_lease():
        with _leased_inbound_upload_gate_sync(upload_id):
            with _leased_upload_lock(upload_id):
                db.rollback()
                _delete_upload_session_locked(db, upload_id)


def delete_upload_sessions_for_owner(db: Session, owner_id: int) -> None:
    uploads = db.execute(select(UploadSession).where(UploadSession.owner_id == owner_id)).scalars().all()
    for upload in uploads:
        cancel_upload_session_internal(db, upload)


def _cleanup_upload_directory(child: Path, stale_before: float) -> bool:
    """Recheck one upload directory under its PUT/cancel gate.

    Returns ``True`` when an untracked directory was removed.  This separate
    helper keeps the snapshot-race invariant directly unit-testable.
    """
    if not child.is_dir():
        return False
    with _leased_inbound_upload_gate_sync(child.name):
        with SessionLocal() as verification_db:
            still_tracked = verification_db.get(UploadSession, child.name) is not None
        if not still_tracked:
            shutil.rmtree(child, ignore_errors=True)
            return True
        # A normally completed request removes its unique temp file in a
        # finally block.  The gate proves no current PUT owns this path; age
        # protects crash leftovers from clock/filesystem anomalies.
        for tmp in child.glob("part-*.tmp"):
            try:
                if tmp.stat().st_mtime <= stale_before:
                    tmp.unlink(missing_ok=True)
            except OSError:
                pass
    return False


@serialized_library_lifecycle
@_serialized(_session_create_lock)
def cleanup_expired_uploads() -> int:
    """Delete expired tracking/temp data and old orphan upload directories."""
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    with SessionLocal() as db:
        expired = db.execute(
            select(UploadSession).where(UploadSession.expires_at <= _now())
        ).scalars().all()
        for upload in expired:
            upload_id = upload.upload_id
            if upload.status in ("verifying", "finalizing"):
                try:
                    if upload.status == "verifying":
                        recover_verifying_session(db, upload)
                    else:
                        recover_finalizing_session(db, upload)
                    db.expire_all()
                    refreshed = _fresh_upload_session(db, upload_id)
                    if refreshed is not None and refreshed.expires_at > _now():
                        continue
                    upload = refreshed or upload
                except OSError:
                    db.rollback()
                    continue
            cancel_upload_session_internal(db, upload)
            removed += 1

        sessions = db.execute(select(UploadSession)).scalars().all()
        known = {upload.upload_id for upload in sessions}

        # Drop orphan/structurally invalid metadata.  Hashing every live video
        # hourly would be prohibitively expensive; full chunk hashes are still
        # rechecked synchronously before finalization.
        parts = db.execute(select(UploadPart)).scalars().all()
        by_upload: dict[str, list[UploadPart]] = {}
        for part in parts:
            if part.upload_id not in known:
                db.delete(part)
            else:
                by_upload.setdefault(part.upload_id, []).append(part)
        for upload in sessions:
            if upload.status != "active":
                continue
            path = session_file(upload.upload_id)
            file_size = path.stat().st_size if path.is_file() else 0
            for part in by_upload.get(upload.upload_id, []):
                expected_offset = part.part_number * upload.chunk_size
                expected_size = (
                    min(upload.chunk_size, upload.size - expected_offset)
                    if 0 <= part.part_number < upload.total_parts
                    else -1
                )
                if (
                    part.offset != expected_offset
                    or part.size != expected_size
                    or part.offset + part.size > file_size
                    or not _SHA256_RE.fullmatch(part.sha256)
                ):
                    db.delete(part)
        db.commit()
    stale_before = time.time() - max(60, settings.video_cleanup_interval_seconds)
    for child in settings.uploads_dir.iterdir():
        # ``known`` is only a snapshot.  Serialize with PUT/cancel, then query
        # again before destructive filesystem work.  The outer create lock
        # also spans session commit + mkdir, closing the new-session window.
        _cleanup_upload_directory(child, stale_before)
    return removed


@serialized_library_lifecycle
@_serialized(_session_create_lock)
@_serialized(_finalization_lock)
def dissolve_team_media(db: Session, team: Team) -> None:
    """Atomically return team media/sessions to uploaders and delete a team.

    The create lock prevents a checked-but-not-yet-inserted team upload from
    appearing after dissolution.  The finalization lock makes either the
    completed video or this migration win first; both orders end with a NULL
    team id.  No new database foreign key is involved.
    """
    team_id = team.id
    db.rollback()
    current = db.get(Team, team_id)
    if current is None:
        return
    # Team groups are shared-space organization metadata. Once media is
    # returned to each uploader's personal space, keeping a mixed-owner group
    # would violate the scope invariant, so groups/items are removed explicitly.
    delete_team_groups(db, team_id)
    db.execute(update(Image).where(Image.team_id == team_id).values(team_id=None))
    db.execute(
        update(UploadSession).where(UploadSession.team_id == team_id).values(team_id=None)
    )
    db.delete(current)
    db.commit()

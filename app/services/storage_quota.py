"""Reusable per-user and per-team storage accounting and admission checks."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import Image, UploadSession

# Failed sessions remain discoverable/cancelable and continue reserving their
# declared bytes until cancellation or expiry removes them.
RESERVED_UPLOAD_STATUSES = ("active", "verifying", "finalizing", "failed")


def _now():
    """SQLite stores UTC timestamps without timezone information."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def user_storage_usage_bytes(db: Session, owner_id: int) -> int:
    """Completed personal/team media plus unfinished reservations for a user."""
    completed = db.scalar(
        select(func.coalesce(func.sum(Image.size), 0)).where(Image.owner_id == owner_id)
    ) or 0
    reserved = db.scalar(
        select(func.coalesce(func.sum(UploadSession.size), 0)).where(
            UploadSession.owner_id == owner_id,
            UploadSession.status.in_(RESERVED_UPLOAD_STATUSES),
            UploadSession.expires_at > _now(),
        )
    ) or 0
    return int(completed) + int(reserved)


def team_storage_usage_bytes(db: Session, team_id: int) -> int:
    """Completed media plus unfinished reservations in one team space."""
    completed = db.scalar(
        select(func.coalesce(func.sum(Image.size), 0)).where(Image.team_id == team_id)
    ) or 0
    reserved = db.scalar(
        select(func.coalesce(func.sum(UploadSession.size), 0)).where(
            UploadSession.team_id == team_id,
            UploadSession.status.in_(RESERVED_UPLOAD_STATUSES),
            UploadSession.expires_at > _now(),
        )
    ) or 0
    return int(completed) + int(reserved)


def enforce_storage_quota(
    db: Session,
    *,
    owner_id: int,
    team_id: int | None,
    additional_bytes: int,
) -> None:
    """Reject a new image/session that would cross configured tenant limits.

    Callers hold the global library lifecycle lease, making the read-plus-write
    admission decision atomic within the documented single-worker boundary.
    """
    additional = max(0, int(additional_bytes))
    user_limit = settings.user_storage_quota_bytes
    if user_limit and user_storage_usage_bytes(db, owner_id) + additional > user_limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="user storage quota exceeded",
        )

    team_limit = settings.team_storage_quota_bytes
    if (
        team_id is not None
        and team_limit
        and team_storage_usage_bytes(db, team_id) + additional > team_limit
    ):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="team storage quota exceeded",
        )

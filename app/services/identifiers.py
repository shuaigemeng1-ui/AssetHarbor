"""Durable monotonic identifier allocation for SQLite rows exposed by the API."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import MediaGroup, RuntimeCounter, Team, TeamMember, User
from ..models.base import utcnow

_MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991


def _next_id(db: Session, model, counter_name: str, label: str) -> int:
    live_max = db.scalar(select(func.max(model.id))) or 0
    counter = db.get(RuntimeCounter, counter_name)
    next_id = max(int(live_max), int(counter.value) if counter is not None else 0) + 1
    if next_id > _MAX_SAFE_JSON_INTEGER:
        raise HTTPException(status_code=503, detail=f"{label} identifier space exhausted")
    if counter is None:
        db.add(RuntimeCounter(name=counter_name, value=next_id, updated_at=utcnow()))
    else:
        counter.value = next_id
        counter.updated_at = utcnow()
    return next_id


def next_user_id(db: Session) -> int:
    """Reserve a user ID that remains unique after deletion and on legacy DBs.

    Callers hold the process-wide library lifecycle lease, which also covers
    account deletion. The counter table has no foreign keys and survives user
    removal, unlike SQLite's default reusable ``INTEGER PRIMARY KEY``.
    """
    return _next_id(db, User, "user_id", "user")


def next_team_id(db: Session) -> int:
    """Reserve a team ID so stale numeric-URL retries cannot target a new team."""
    return _next_id(db, Team, "team_id", "team")


def next_team_member_id(db: Session) -> int:
    """Reserve a membership ID so stale role/removal retries cannot hit a replacement."""
    return _next_id(db, TeamMember, "team_member_id", "team membership")


def next_media_group_id(db: Session) -> int:
    """Reserve a media-group ID so stale PATCH/DELETE retries stay harmless."""
    return _next_id(db, MediaGroup, "media_group_id", "media group")

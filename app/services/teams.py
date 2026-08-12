"""Team membership helpers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TeamMember


def get_membership(db: Session, team_id: int, user_id: int) -> TeamMember | None:
    return db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    ).scalar_one_or_none()


def is_team_member(db: Session, team_id: int, user_id: int) -> bool:
    return get_membership(db, team_id, user_id) is not None


def can_manage_team(db: Session, team_id: int, user_id: int, *, require_owner: bool = False) -> bool:
    """Whether the user can administer a team (owner/admin, or owner only)."""
    member = get_membership(db, team_id, user_id)
    if member is None:
        return False
    if require_owner:
        return member.role == "owner"
    return member.role in ("owner", "admin")

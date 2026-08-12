"""Team membership: invite by username, remove, change roles."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....models import TeamMember, User
from ....schemas import AddMember, RoleUpdate, TeamMemberOut
from ....services.library import (
    fresh_library_user,
    serialized_library_lifecycle,
    transfer_member_groups,
)
from ....services.teams import can_manage_team, get_membership
from ...deps import get_current_user, get_db
from ._common import get_team_or_404, member_out

router = APIRouter(prefix="/api", tags=["teams"])

_TEAM_ROLES = ("member", "admin")


@router.post(
    "/teams/{team_id}/members",
    response_model=TeamMemberOut,
    status_code=201,
    summary="Add a member by username (owner/team-admin/global-admin)",
)
@serialized_library_lifecycle
def add_member(
    team_id: int,
    payload: AddMember,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    team = get_team_or_404(db, team_id)
    if not can_manage_team(db, team.id, current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="team admin privileges required")

    target = db.execute(
        select(User).where(User.username == payload.username.strip())
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    if target.id == team.owner_id:
        raise HTTPException(status_code=409, detail="the team owner is already a member")
    if get_membership(db, team.id, target.id) is not None:
        raise HTTPException(status_code=409, detail="user is already a member")

    tm = TeamMember(team_id=team.id, user_id=target.id, role="member")
    db.add(tm)
    db.commit()
    db.refresh(tm)
    return member_out(tm, target.username)


@router.delete(
    "/teams/{team_id}/members/{member_id}",
    status_code=204,
    summary="Remove a member (owner/team-admin/global-admin)",
)
@serialized_library_lifecycle
def remove_member(
    team_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Resolve the target under the shared lifecycle lease before authorizing;
    # a non-owner member may leave voluntarily, while removing somebody else
    # still requires a team/global administrator.
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    team = get_team_or_404(db, team_id)
    tm = db.get(TeamMember, member_id)
    if tm is None or tm.team_id != team.id:
        raise HTTPException(status_code=404, detail="member not found")
    if tm.user_id == team.owner_id:
        raise HTTPException(status_code=400, detail="cannot remove the team owner")
    leaving_self = tm.user_id == current_user.id
    if (
        not leaving_self
        and not can_manage_team(db, team.id, current_user.id)
        and current_user.role != "admin"
    ):
        raise HTTPException(status_code=403, detail="team admin privileges required")

    transfer_member_groups(db, team, tm.user_id)
    db.delete(tm)
    db.commit()


@router.patch(
    "/teams/{team_id}/members/{member_id}",
    response_model=TeamMemberOut,
    summary="Change a member's role (owner/global-admin only)",
)
@serialized_library_lifecycle
def change_member_role(
    team_id: int,
    member_id: int,
    payload: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    team = get_team_or_404(db, team_id)
    if not can_manage_team(db, team.id, current_user.id, require_owner=True) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="team owner privileges required")
    if payload.role not in _TEAM_ROLES:
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")

    tm = db.get(TeamMember, member_id)
    if tm is None or tm.team_id != team.id:
        raise HTTPException(status_code=404, detail="member not found")
    if tm.user_id == team.owner_id:
        raise HTTPException(status_code=400, detail="cannot change the team owner's role")

    tm.role = payload.role
    db.commit()
    db.refresh(tm)
    return member_out(tm, db.get(User, tm.user_id).username)

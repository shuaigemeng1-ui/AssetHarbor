"""Admin-only endpoints: stats, user role management, team overview."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Image, Team, TeamMember, User
from ..schemas import AdminStats, ResetPasswordRequest, RoleUpdate, TeamAdminOut, UserOut
from ..security import hash_password, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.get("/stats", response_model=AdminStats, summary="System statistics (admin)")
def admin_stats(db: Session = Depends(get_db)) -> AdminStats:
    users = db.scalar(select(func.count()).select_from(User)) or 0
    images = db.scalar(select(func.count()).select_from(Image)) or 0
    teams = db.scalar(select(func.count()).select_from(Team)) or 0
    storage = db.scalar(select(func.coalesce(func.sum(Image.size), 0))) or 0
    return AdminStats(users=users, images=images, teams=teams, storage_bytes=storage)


@router.get("/teams", response_model=list[TeamAdminOut], summary="All teams with member counts (admin)")
def admin_teams(db: Session = Depends(get_db)) -> list[TeamAdminOut]:
    rows = db.execute(
        select(Team, User.username).join(User, User.id == Team.owner_id).order_by(Team.id)
    ).all()
    if not rows:
        return []
    team_ids = [team.id for team, _ in rows]
    counts = dict(
        db.execute(
            select(TeamMember.team_id, func.count())
            .where(TeamMember.team_id.in_(team_ids))
            .group_by(TeamMember.team_id)
        ).all()
    )
    return [
        TeamAdminOut(
            id=team.id,
            name=team.name,
            description=team.description,
            owner_username=owner_name,
            member_count=counts.get(team.id, 0),
            created_at=team.created_at,
        )
        for team, owner_name in rows
    ]


@router.patch("/users/{user_id}/role", response_model=UserOut, summary="Set a user's global role (admin)")
def set_user_role(
    user_id: int,
    payload: RoleUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'user'")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot change your own role")

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    target.role = payload.role
    db.commit()
    db.refresh(target)
    return _user_out(target)


@router.patch("/users/{user_id}/password", status_code=204, summary="Reset a user's password (admin)")
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    target.password_hash = hash_password(payload.new_password)
    db.commit()

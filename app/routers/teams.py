"""Teams: creation, membership management, and the team image space."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Image, Team, TeamMember, User
from ..schemas import (
    AddMember,
    ImageInfo,
    ImageListResponse,
    RoleUpdate,
    TeamCreate,
    TeamDetail,
    TeamMemberOut,
    TeamOut,
)
from ..security import get_current_user
from ..services.teams import can_manage_team, get_membership
from ..urls import build_image_url

router = APIRouter(prefix="/api", tags=["teams"])

_TEAM_ROLES = ("member", "admin")


def _team_out(team: Team, my_role: str, member_count: int, owner_name: str | None) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        role=my_role,
        member_count=member_count,
        owner_username=owner_name,
        created_at=team.created_at,
    )


def _member_out(tm: TeamMember, username: str) -> TeamMemberOut:
    return TeamMemberOut(id=tm.id, username=username, role=tm.role, created_at=tm.created_at)


def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return team


@router.post("/teams", response_model=TeamOut, status_code=201, summary="Create a team")
def create_team(
    payload: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamOut:
    name = payload.name.strip()
    if db.execute(select(Team.id).where(Team.name == name)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="team name already taken")

    team = Team(name=name, description=payload.description.strip(), owner_id=current_user.id)
    db.add(team)
    db.flush()  # get team.id
    db.add(TeamMember(team_id=team.id, user_id=current_user.id, role="owner"))
    db.commit()
    db.refresh(team)
    return _team_out(team, "owner", 1, current_user.username)


@router.get("/teams", response_model=list[TeamOut], summary="List teams I belong to")
def list_my_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamOut]:
    rows = db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current_user.id)
        .order_by(Team.id)
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
    owner_ids = {team.owner_id for team, _ in rows}
    owner_names = dict(
        db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all()
    )
    return [
        _team_out(team, my_role, counts.get(team.id, 0), owner_names.get(team.owner_id))
        for team, my_role in rows
    ]


@router.get("/teams/{team_id}", response_model=TeamDetail, summary="Team detail and members")
def team_detail(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetail:
    team = _get_team_or_404(db, team_id)
    my = get_membership(db, team.id, current_user.id)
    if my is None and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="team not found")

    members = db.execute(
        select(TeamMember, User.username)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team.id)
        .order_by(TeamMember.role, TeamMember.id)
    ).all()
    owner_name = db.get(User, team.owner_id).username

    base = _team_out(team, my.role if my else "admin", len(members), owner_name)
    return TeamDetail(
        **base.model_dump(),
        members=[_member_out(tm, uname) for tm, uname in members],
    )


@router.post(
    "/teams/{team_id}/members",
    response_model=TeamMemberOut,
    status_code=201,
    summary="Add a member by username (owner/team-admin/global-admin)",
)
def add_member(
    team_id: int,
    payload: AddMember,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    team = _get_team_or_404(db, team_id)
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
    return _member_out(tm, target.username)


@router.delete(
    "/teams/{team_id}/members/{member_id}",
    status_code=204,
    summary="Remove a member (owner/team-admin/global-admin)",
)
def remove_member(
    team_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    team = _get_team_or_404(db, team_id)
    if not can_manage_team(db, team.id, current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="team admin privileges required")

    tm = db.get(TeamMember, member_id)
    if tm is None or tm.team_id != team.id:
        raise HTTPException(status_code=404, detail="member not found")
    if tm.user_id == team.owner_id:
        raise HTTPException(status_code=400, detail="cannot remove the team owner")

    db.delete(tm)
    db.commit()


@router.patch(
    "/teams/{team_id}/members/{member_id}",
    response_model=TeamMemberOut,
    summary="Change a member's role (owner/global-admin only)",
)
def change_member_role(
    team_id: int,
    member_id: int,
    payload: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberOut:
    team = _get_team_or_404(db, team_id)
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
    return _member_out(tm, db.get(User, tm.user_id).username)


@router.delete("/teams/{team_id}", status_code=204, summary="Delete a team (owner/global-admin)")
def delete_team(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    team = _get_team_or_404(db, team_id)
    if not can_manage_team(db, team.id, current_user.id, require_owner=True) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="team owner privileges required")

    # Images return to their uploader's personal space.
    db.execute(update(Image).where(Image.team_id == team.id).values(team_id=None))
    db.delete(team)  # cascades team_members rows
    db.commit()


@router.get(
    "/teams/{team_id}/images",
    response_model=ImageListResponse,
    summary="Team space images (members/admin only)",
)
def team_images(
    team_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
) -> ImageListResponse:
    team = _get_team_or_404(db, team_id)
    if get_membership(db, team.id, current_user.id) is None and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="team not found")

    filters = [Image.team_id == team.id]
    if q:
        like = f"%{q}%"
        filters.append(
            or_(Image.name.like(like), Image.original_filename.like(like), Image.code.like(like))
        )

    total = db.scalar(select(func.count()).select_from(Image).where(*filters)) or 0
    rows = db.execute(
        select(Image)
        .where(*filters)
        .order_by(Image.created_at.desc(), Image.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    owner_ids = {img.owner_id for img in rows if img.owner_id is not None}
    usernames: dict[int, str] = {}
    if owner_ids:
        usernames = dict(
            db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all()
        )

    items = [
        ImageInfo(
            code=img.code,
            url=build_image_url(request, img.code),
            size=img.size,
            content_type=img.content_type,
            sha256=img.sha256,
            created_at=img.created_at,
            name=img.name,
            visibility=img.visibility,
            owner_id=img.owner_id,
            team_id=img.team_id,
            original_filename=img.original_filename,
            owner_username=usernames.get(img.owner_id) if img.owner_id else None,
        )
        for img in rows
    ]
    return ImageListResponse(items=items, total=total)

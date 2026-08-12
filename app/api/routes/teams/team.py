"""Team CRUD: create, list mine, detail, delete."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....models import Team, TeamMember, User
from ....schemas import TeamCreate, TeamDetail, TeamOut
from ....services.teams import can_manage_team, get_membership
from ....services.library import fresh_library_user, serialized_library_lifecycle
from ....services.videos import dissolve_team_media
from ...deps import get_current_user, get_db
from ._common import get_team_or_404, member_out, team_out

router = APIRouter(prefix="/api", tags=["teams"])


@router.post("/teams", response_model=TeamOut, status_code=201, summary="Create a team")
@serialized_library_lifecycle
def create_team(
    payload: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    name = payload.name.strip()
    if db.execute(select(Team.id).where(Team.name == name)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="team name already taken")

    team = Team(name=name, description=payload.description.strip(), owner_id=current_user.id)
    db.add(team)
    db.flush()  # get team.id
    db.add(TeamMember(team_id=team.id, user_id=current_user.id, role="owner"))
    db.commit()
    db.refresh(team)
    return team_out(team, "owner", 1, current_user.username)


@router.get("/teams", response_model=list[TeamOut], summary="List teams I belong to")
def list_my_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamOut]:
    if current_user.role == "admin":
        rows = [
            (team, "admin")
            for team in db.execute(select(Team).order_by(Team.id)).scalars().all()
        ]
    else:
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
        team_out(team, my_role, counts.get(team.id, 0), owner_names.get(team.owner_id))
        for team, my_role in rows
    ]


@router.get("/teams/{team_id}", response_model=TeamDetail, summary="Team detail and members")
def team_detail(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetail:
    team = get_team_or_404(db, team_id)
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

    base = team_out(team, my.role if my else "admin", len(members), owner_name)
    return TeamDetail(
        **base.model_dump(),
        members=[member_out(tm, uname) for tm, uname in members],
    )


@router.delete("/teams/{team_id}", status_code=204, summary="Delete a team (owner/global-admin)")
@serialized_library_lifecycle
def delete_team(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    team = get_team_or_404(db, team_id)
    if not can_manage_team(db, team.id, current_user.id, require_owner=True) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="team owner privileges required")

    dissolve_team_media(db, team)

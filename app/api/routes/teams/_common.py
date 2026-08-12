"""Shared helpers for the team routes."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ....models import Team, TeamMember
from ....schemas import TeamMemberOut, TeamOut


def get_team_or_404(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return team


def team_out(team: Team, my_role: str, member_count: int, owner_name: str | None) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        role=my_role,
        member_count=member_count,
        owner_username=owner_name,
        created_at=team.created_at,
    )


def member_out(tm: TeamMember, username: str) -> TeamMemberOut:
    return TeamMemberOut(id=tm.id, username=username, role=tm.role, created_at=tm.created_at)

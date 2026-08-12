"""Team space: the team-shared image gallery."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ....models import Image, User
from ....schemas import ImageInfo, ImageListResponse
from ....services.signing import build_image_url
from ....services.teams import get_membership
from ...deps import get_current_user, get_db
from ._common import get_team_or_404

router = APIRouter(prefix="/api", tags=["teams"])


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
    team = get_team_or_404(db, team_id)
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

"""Upload API (requires authentication)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ...core.config import settings
from ...models import Team, User
from ...schemas import UploadResponse
from ...services.images import store_upload
from ...services.ratelimit import check_rate_limit
from ...services.signing import build_image_url
from ...services.teams import get_membership
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api", tags=["upload"])

_VISIBILITIES = ("public", "private")


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=201,
    summary="Upload an image",
    description="Uploads an image (optionally named, public or private, to your "
    "space or a team space) and returns its short-code URL.",
)
async def upload_image(
    request: Request,
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(..., description="Image file (jpeg/png/gif/webp/svg/bmp/ico/avif/tiff)"),
    name: str = Form("", description="Optional display name; falls back to the filename"),
    visibility: str = Form(settings.default_visibility, description="public (anyone) or private (owner + team + signed links only)"),
    team_id: int | None = Form(None, description="Team space to upload into (optional)"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    check_rate_limit(f"upload:{current_user.id}", settings.upload_rate_limit_per_minute, 60)

    if visibility not in _VISIBILITIES:
        raise HTTPException(status_code=422, detail="visibility must be 'public' or 'private'")

    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="team not found")
        if get_membership(db, team.id, current_user.id) is None and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="you are not a member of this team")

    image = await store_upload(
        file, db, owner=current_user, name=name.strip() or None, visibility=visibility, team_id=team_id
    )
    return UploadResponse(
        code=image.code,
        url=build_image_url(request, image.code),
        size=image.size,
        content_type=image.content_type,
        sha256=image.sha256,
        created_at=image.created_at,
        name=image.name,
        visibility=image.visibility,
        owner_id=image.owner_id,
        team_id=image.team_id,
    )

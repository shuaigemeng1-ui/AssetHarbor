"""Upload API (requires authentication)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import UploadResponse
from ..security import get_current_user
from ..services.images import store_upload
from ..services.ratelimit import check_rate_limit
from ..urls import build_image_url

router = APIRouter(prefix="/api", tags=["upload"])

_VISIBILITIES = ("public", "private")


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=201,
    summary="Upload an image",
    description="Uploads an image (optionally named, public or private) and returns its short-code URL.",
)
async def upload_image(
    request: Request,
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(..., description="Image file (jpeg/png/gif/webp/svg/bmp/ico/avif/tiff)"),
    name: str = Form("", description="Optional display name; falls back to the filename"),
    visibility: str = Form(settings.default_visibility, description="public (anyone) or private (owner + admins + signed links only)"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    check_rate_limit(f"upload:{current_user.id}", settings.upload_rate_limit_per_minute, 60)

    if visibility not in _VISIBILITIES:
        raise HTTPException(status_code=422, detail="visibility must be 'public' or 'private'")

    image = await store_upload(file, db, owner=current_user, name=name.strip() or None, visibility=visibility)
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
    )

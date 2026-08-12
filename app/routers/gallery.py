"""Gallery API: list images with per-user isolation, search and pagination."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Image, User
from ..schemas import ImageInfo, ImageListResponse
from ..security import get_current_user
from ..urls import build_image_url

router = APIRouter(prefix="/api", tags=["gallery"])


@router.get(
    "/images",
    response_model=ImageListResponse,
    summary="List images (your own, or all if admin)",
    description="Newest first. Regular users only see their own images; admins see "
    "everything. Supports text search via ?q= and limit/offset pagination.",
)
def list_images(
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    q: str = Query("", max_length=100, description="Search name / filename / code"),
    db: Session = Depends(get_db),
) -> ImageListResponse:
    filters = []
    if current_user.role != "admin":
        filters.append(Image.owner_id == current_user.id)
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

    # Batch-fetch owner usernames (for the admin all-images view).
    owner_ids = {img.owner_id for img in rows if img.owner_id is not None}
    usernames: dict[int, str] = {}
    if owner_ids:
        owners = db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all()
        usernames = {uid: uname for uid, uname in owners}

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
            original_filename=img.original_filename,
            owner_username=usernames.get(img.owner_id) if img.owner_id else None,
        )
        for img in rows
    ]
    return ImageListResponse(items=items, total=total)

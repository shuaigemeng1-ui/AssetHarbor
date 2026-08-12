"""Gallery API: list images with per-user isolation, search, pagination, signed links."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...models import Image, User
from ...schemas import ImageInfo, ImageListResponse, ImageUpdate, SignedLinkResponse
from ...services.images import can_manage_image, delete_image, update_media_metadata
from ...services.signing import build_image_url, build_signed_image_url
from ...services.teams import is_team_member
from ..deps import get_current_user, get_db

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
    filters = [Image.media_kind == "image"]
    if current_user.role != "admin":
        filters.append(Image.owner_id == current_user.id)
        filters.append(Image.team_id.is_(None))  # team images live in the team space
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
            team_id=img.team_id,
            original_filename=img.original_filename,
            owner_username=usernames.get(img.owner_id) if img.owner_id else None,
        )
        for img in rows
    ]
    return ImageListResponse(items=items, total=total)


@router.delete(
    "/images/{code}", status_code=204, summary="Delete an image (owner/admin/team-manager)"
)
def delete_image_endpoint(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    image = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == "image")
    ).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    if not can_manage_image(db, current_user, image):
        raise HTTPException(status_code=403, detail="you can only delete images you manage")
    delete_image(db, image, current_user)


@router.patch(
    "/images/{code}",
    response_model=ImageInfo,
    summary="Update an image's name/visibility (owner/admin/team-manager)",
)
def update_image_endpoint(
    code: str,
    request: Request,
    payload: ImageUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageInfo:
    image = update_media_metadata(
        db,
        code=code,
        media_kind="image",
        actor=current_user,
        name=payload.name,
        visibility=payload.visibility,
    )

    owner_username = None
    if image.owner_id is not None:
        owner = db.get(User, image.owner_id)
        owner_username = owner.username if owner else None

    return ImageInfo(
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
        original_filename=image.original_filename,
        owner_username=owner_username,
    )


@router.get(
    "/images/{code}/link",
    response_model=SignedLinkResponse,
    summary="Get an expiring signed URL (owner/admin/team-member)",
    description="Returns a time-limited signed URL for an image. Required to view "
    "private images outside the browser session (e.g. <img> tags or sharing).",
)
def get_signed_link(
    code: str,
    request: Request,
    ttl: int = Query(settings.signed_url_ttl_seconds, ge=60, le=7 * 86400, description="TTL in seconds"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SignedLinkResponse:
    image = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == "image")
    ).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")

    is_owner = image.owner_id == current_user.id
    is_admin = current_user.role == "admin"
    in_team = bool(
        image.team_id is not None and is_team_member(db, image.team_id, current_user.id)
    )
    if not (is_owner or is_admin or in_team):
        # 404 (not 403): don't reveal that the image exists.
        raise HTTPException(status_code=404, detail="image not found")

    url, expires = build_signed_image_url(
        request, image.code, ttl_seconds=ttl, version=image.signing_version
    )
    return SignedLinkResponse(url=url, expires_at=datetime.fromtimestamp(expires, tz=timezone.utc))

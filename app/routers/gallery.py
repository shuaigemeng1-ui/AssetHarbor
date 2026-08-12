"""Gallery API: list previously uploaded images."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Image
from ..schemas import ImageInfo, ImageListResponse
from ..urls import build_image_url

router = APIRouter(prefix="/api", tags=["gallery"])


@router.get(
    "/images",
    response_model=ImageListResponse,
    summary="List uploaded images",
    description="Returns image metadata (newest first) with public short-code URLs.",
)
def list_images(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> ImageListResponse:
    total = db.scalar(select(func.count()).select_from(Image)) or 0
    rows = db.execute(
        select(Image)
        .order_by(Image.created_at.desc(), Image.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    items = [
        ImageInfo(
            code=img.code,
            url=build_image_url(request, img.code),
            size=img.size,
            content_type=img.content_type,
            sha256=img.sha256,
            created_at=img.created_at,
            original_filename=img.original_filename,
        )
        for img in rows
    ]
    return ImageListResponse(items=items, total=total)

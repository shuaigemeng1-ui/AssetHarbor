"""Upload API."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import UploadResponse
from ..services.images import store_upload
from ..urls import build_image_url

router = APIRouter(prefix="/api", tags=["upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=201,
    summary="Upload an image",
    description="Uploads an image file and returns its short-code URL.",
)
async def upload_image(
    request: Request,
    file: UploadFile = File(..., description="Image file (jpeg/png/gif/webp/svg/bmp/ico/avif/tiff)"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    image = await store_upload(file, db)
    return UploadResponse(
        code=image.code,
        url=build_image_url(request, image.code),
        size=image.size,
        content_type=image.content_type,
        sha256=image.sha256,
        created_at=image.created_at,
    )

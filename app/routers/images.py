"""Public image serving: GET /i/{code}."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Image

router = APIRouter(tags=["images"])

_IMMUTABLE_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}
_SVG_HEADERS = {
    # SVG can embed scripts — never render it inline in the MVP.
    "Content-Disposition": 'attachment; filename="image.svg"',
    "X-Content-Type-Options": "nosniff",
}


@router.get("/i/{code}", summary="Fetch an image by short code")
def get_image(code: str, db: Session = Depends(get_db)):
    image = db.execute(select(Image).where(Image.code == code)).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")

    path = settings.data_dir / image.stored_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")

    headers = dict(_IMMUTABLE_CACHE)
    if image.content_type == "image/svg+xml":
        headers.update(_SVG_HEADERS)

    return FileResponse(path, media_type=image.content_type, headers=headers)

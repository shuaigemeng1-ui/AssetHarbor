"""Public image serving: GET /i/{code} (with visibility enforcement)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Image, User
from ..security import get_optional_user

router = APIRouter(tags=["images"])

_IMMUTABLE_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}
_SVG_HEADERS = {
    # SVG can embed scripts — never render it inline in the MVP.
    "Content-Disposition": 'attachment; filename="image.svg"',
    "X-Content-Type-Options": "nosniff",
}


@router.get("/i/{code}", summary="Fetch an image by short code")
def get_image(
    code: str,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    image = db.execute(select(Image).where(Image.code == code)).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")

    if image.visibility == "private":
        is_owner = current_user is not None and image.owner_id == current_user.id
        is_admin = current_user is not None and current_user.role == "admin"
        if not (is_owner or is_admin):
            # 404 (not 403) so private images are not discoverable.
            raise HTTPException(status_code=404, detail="image not found")

    path = settings.data_dir / image.stored_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")

    headers = dict(_IMMUTABLE_CACHE)
    if image.content_type == "image/svg+xml":
        headers.update(_SVG_HEADERS)

    return FileResponse(path, media_type=image.content_type, headers=headers)

"""Public image serving: GET /i/{code} (visibility + signed URLs + rate limit)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.auth_scope import has_global_admin_scope
from ...models import Image, User
from ...services.ratelimit import check_rate_limit, client_ip
from ...services.signing import verify_image_signature
from ...services.storage_paths import resolve_media_path
from ...services.teams import is_team_member
from ..deps import get_db, get_optional_user

router = APIRouter(tags=["images"])

_PUBLIC_REVALIDATE_CACHE = {"Cache-Control": "public, max-age=0, must-revalidate"}
_SVG_HEADERS = {
    # SVG can embed scripts — never render it inline in the MVP.
    "Content-Disposition": 'attachment; filename="image.svg"',
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'",
}


@router.get("/i/{code}", summary="Fetch an image by short code")
def get_image(
    code: str,
    request: Request,
    expires: str | None = None,
    sig: str | None = None,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    # Throttle code-scanning attempts regardless of whether the code exists.
    check_rate_limit(f"img:{client_ip(request)}", settings.images_rate_limit_per_minute, 60)

    image = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == "image")
    ).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")

    if image.visibility == "private":
        is_owner = bool(
            current_user is not None
            and image.team_id is None
            and image.owner_id == current_user.id
        )
        is_admin = has_global_admin_scope(current_user)
        in_team = bool(
            image.team_id is not None
            and current_user is not None
            and is_team_member(db, image.team_id, current_user.id)
        )
        has_valid_link = bool(
            expires
            and sig
            and verify_image_signature(image.code, expires, sig, image.signing_version)
        )
        if not (is_owner or is_admin or in_team or has_valid_link):
            # 404 (not 403) so private images are not discoverable.
            raise HTTPException(status_code=404, detail="image not found")

    try:
        path = resolve_media_path(image.stored_path)
    except ValueError:
        raise HTTPException(status_code=404, detail="image not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")

    if image.visibility == "private":
        # Never cache private images: once cached with a long/immutable lifetime,
        # a browser would keep showing them even after they are revoked.
        headers = {"Cache-Control": "private, no-store, max-age=0"}
    else:
        headers = dict(_PUBLIC_REVALIDATE_CACHE)
    if image.content_type == "image/svg+xml":
        headers.update(_SVG_HEADERS)

    return FileResponse(path, media_type=image.content_type, headers=headers)

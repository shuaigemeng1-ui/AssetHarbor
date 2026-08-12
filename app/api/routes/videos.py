"""Resumable video upload, video gallery and byte-range delivery APIs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...models import Image, Team, UploadSession, User
from ...schemas import (
    SignedLinkResponse,
    VideoInfo,
    VideoListResponse,
    VideoPartResponse,
    VideoUpdate,
    VideoUploadCreate,
    VideoUploadStatus,
)
from ...services.images import can_manage_image, delete_image
from ...services.ratelimit import check_rate_limit, client_ip
from ...services.signing import (
    build_signed_video_url,
    build_video_url,
    verify_image_signature,
)
from ...services.teams import get_membership, is_team_member
from ...services.videos import (
    cancel_upload_session,
    complete_upload_session,
    create_upload_session,
    get_upload_for_user,
    store_upload_part,
    uploaded_part_numbers,
)
from ..deps import get_current_user, get_db, get_optional_user

router = APIRouter(tags=["videos"])
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _video_info(request: Request, video: Image, owner_username: str | None = None) -> VideoInfo:
    return VideoInfo(
        code=video.code,
        url=build_video_url(request, video.code),
        size=video.size,
        content_type=video.content_type,
        sha256=video.sha256,
        created_at=video.created_at,
        name=video.name,
        visibility=video.visibility,
        owner_id=video.owner_id,
        team_id=video.team_id,
        original_filename=video.original_filename,
        owner_username=owner_username,
        media_kind="video",
    )


def _status_response(request: Request, db: Session, upload: UploadSession) -> VideoUploadStatus:
    video = None
    if upload.status == "completed" and upload.final_code:
        row = db.execute(
            select(Image).where(Image.code == upload.final_code, Image.media_kind == "video")
        ).scalar_one_or_none()
        if row is not None:
            owner = db.get(User, row.owner_id) if row.owner_id is not None else None
            video = _video_info(request, row, owner.username if owner else None)
    return VideoUploadStatus(
        upload_id=upload.upload_id,
        team_id=upload.team_id,
        chunk_size=upload.chunk_size,
        total_parts=upload.total_parts,
        status=upload.status,
        uploaded_parts=uploaded_part_numbers(db, upload.upload_id),
        expires_at=upload.expires_at,
        video=video,
    )


@router.post(
    "/api/video-uploads",
    response_model=VideoUploadStatus,
    status_code=201,
    summary="Initialize or resume a chunked video upload",
)
def initialize_video_upload(
    request: Request,
    payload: VideoUploadCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoUploadStatus:
    check_rate_limit(f"upload:{current_user.id}", settings.upload_rate_limit_per_minute, 60)
    upload = create_upload_session(
        db,
        current_user,
        filename=payload.filename,
        size=payload.size,
        name=payload.name,
        visibility=payload.visibility or settings.default_visibility,
        team_id=payload.team_id,
        fingerprint=payload.fingerprint,
    )
    return _status_response(request, db, upload)


@router.get(
    "/api/video-uploads/{upload_id}",
    response_model=VideoUploadStatus,
    summary="Get authoritative uploaded-part state",
)
def get_video_upload_status(
    upload_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoUploadStatus:
    upload = get_upload_for_user(db, upload_id, current_user)
    return _status_response(request, db, upload)


@router.put(
    "/api/video-uploads/{upload_id}/parts/{part_number}",
    response_model=VideoPartResponse,
    summary="Upload one raw video chunk",
)
async def upload_video_part(
    upload_id: str,
    part_number: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    content_range: str | None = Header(default=None, alias="Content-Range"),
    chunk_sha256: str | None = Header(default=None, alias="X-Chunk-SHA256"),
) -> VideoPartResponse:
    upload = get_upload_for_user(
        db, upload_id, current_user, cleanup_expired=False
    )
    part = await store_upload_part(
        db, upload, part_number, request, content_range, chunk_sha256
    )
    return VideoPartResponse(part_number=part.part_number, size=part.size, sha256=part.sha256)


@router.post(
    "/api/video-uploads/{upload_id}/complete",
    response_model=VideoInfo,
    summary="Validate and atomically finalize a video upload",
)
def complete_video_upload(
    upload_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoInfo:
    upload = get_upload_for_user(db, upload_id, current_user)
    video = complete_upload_session(db, upload, current_user)
    owner = db.get(User, video.owner_id) if video.owner_id is not None else None
    return _video_info(request, video, owner.username if owner else None)


@router.delete(
    "/api/video-uploads/{upload_id}",
    status_code=204,
    summary="Cancel an upload without deleting an already finalized video",
)
def cancel_video_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    upload = get_upload_for_user(db, upload_id, current_user)
    cancel_upload_session(db, upload)


def _list_videos(
    request: Request,
    db: Session,
    filters: list,
    limit: int,
    offset: int,
) -> VideoListResponse:
    filters = [Image.media_kind == "video", *filters]
    total = db.scalar(select(func.count()).select_from(Image).where(*filters)) or 0
    rows = db.execute(
        select(Image)
        .where(*filters)
        .order_by(Image.created_at.desc(), Image.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    owner_ids = {row.owner_id for row in rows if row.owner_id is not None}
    usernames = dict(
        db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all()
    ) if owner_ids else {}
    return VideoListResponse(
        items=[_video_info(request, row, usernames.get(row.owner_id)) for row in rows],
        total=total,
    )


@router.get("/api/videos", response_model=VideoListResponse, summary="List videos")
def list_videos(
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
) -> VideoListResponse:
    filters = []
    if current_user.role != "admin":
        filters.extend((Image.owner_id == current_user.id, Image.team_id.is_(None)))
    if q:
        like = f"%{q}%"
        filters.append(or_(Image.name.like(like), Image.original_filename.like(like), Image.code.like(like)))
    return _list_videos(request, db, filters, limit, offset)


@router.get(
    "/api/teams/{team_id}/videos",
    response_model=VideoListResponse,
    summary="List a team's videos",
)
def list_team_videos(
    team_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
) -> VideoListResponse:
    if db.get(Team, team_id) is None:
        raise HTTPException(status_code=404, detail="team not found")
    if current_user.role != "admin" and get_membership(db, team_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="team not found")
    filters = [Image.team_id == team_id]
    if q:
        like = f"%{q}%"
        filters.append(or_(Image.name.like(like), Image.original_filename.like(like), Image.code.like(like)))
    return _list_videos(request, db, filters, limit, offset)


def _managed_video(db: Session, code: str, user: User) -> Image:
    video = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == "video")
    ).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    if not can_manage_image(db, user, video):
        raise HTTPException(status_code=403, detail="you can only modify videos you manage")
    return video


@router.patch("/api/videos/{code}", response_model=VideoInfo, summary="Update video metadata")
def update_video(
    code: str,
    payload: VideoUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoInfo:
    video = _managed_video(db, code, current_user)
    was_private = video.visibility == "private"
    if payload.visibility is not None:
        if payload.visibility not in ("public", "private"):
            raise HTTPException(status_code=422, detail="visibility must be 'public' or 'private'")
        if payload.visibility != video.visibility:
            video.visibility = payload.visibility
            if payload.visibility == "private" and not was_private:
                video.signing_version += 1
    if payload.name is not None:
        video.name = payload.name.strip() or video.name
    db.commit()
    db.refresh(video)
    owner = db.get(User, video.owner_id) if video.owner_id is not None else None
    return _video_info(request, video, owner.username if owner else None)


@router.delete("/api/videos/{code}", status_code=204, summary="Delete a video")
def delete_video(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    video = _managed_video(db, code, current_user)
    delete_image(db, video)


@router.get(
    "/api/videos/{code}/link",
    response_model=SignedLinkResponse,
    summary="Get an expiring signed video URL",
)
def get_video_signed_link(
    code: str,
    request: Request,
    ttl: int = Query(settings.signed_url_ttl_seconds, ge=60, le=7 * 86400),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SignedLinkResponse:
    video = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == "video")
    ).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    allowed = (
        video.owner_id == current_user.id
        or current_user.role == "admin"
        or (video.team_id is not None and is_team_member(db, video.team_id, current_user.id))
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="video not found")
    url, expires = build_signed_video_url(request, code, ttl, video.signing_version)
    return SignedLinkResponse(url=url, expires_at=datetime.fromtimestamp(expires, tz=timezone.utc))


def _parse_range(value: str, size: int) -> tuple[int, int]:
    if "," in value:
        raise ValueError("multiple ranges are not supported")
    match = _RANGE_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("invalid range")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise ValueError("empty range")
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("invalid suffix")
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
        if start >= size or end < start:
            raise ValueError("range is outside file")
        end = min(end, size - 1)
    return start, end


def _range_stream(path: Path, start: int, end: int):
    remaining = end - start + 1
    with path.open("rb") as file:
        file.seek(start)
        while remaining:
            block = file.read(min(256 * 1024, remaining))
            if not block:
                break
            remaining -= len(block)
            yield block


def _download_header(filename: str) -> str:
    fallback = "".join(ch if ch.isascii() and (ch.isalnum() or ch in ".-_") else "_" for ch in filename)
    fallback = fallback or "video"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/v/{code}", summary="Stream or download a video with byte-range support")
def get_video(
    code: str,
    request: Request,
    expires: str | None = None,
    sig: str | None = None,
    download: bool = False,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    check_rate_limit(f"video:{client_ip(request)}", settings.images_rate_limit_per_minute, 60)
    video = db.execute(
        select(Image).where(Image.code == code, Image.media_kind == "video")
    ).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    if video.visibility == "private":
        allowed = bool(
            (current_user is not None and (video.owner_id == current_user.id or current_user.role == "admin"))
            or (
                video.team_id is not None
                and current_user is not None
                and is_team_member(db, video.team_id, current_user.id)
            )
            or (
                expires
                and sig
                and verify_image_signature(code, expires, sig, video.signing_version)
            )
        )
        if not allowed:
            raise HTTPException(status_code=404, detail="video not found")

    path = settings.data_dir / video.stored_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="video not found")
    headers = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": (
            "private, no-store, max-age=0"
            if video.visibility == "private"
            else "public, max-age=31536000, immutable"
        ),
    }
    if download:
        headers["Content-Disposition"] = _download_header(video.original_filename)

    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path,
            media_type=video.content_type,
            headers=headers,
            filename=video.original_filename if download else None,
        )
    try:
        start, end = _parse_range(range_header, video.size)
    except (ValueError, OverflowError):
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="requested range is not satisfiable",
            headers={**headers, "Content-Range": f"bytes */{video.size}"},
        )
    headers.update(
        {
            "Content-Range": f"bytes {start}-{end}/{video.size}",
            "Content-Length": str(end - start + 1),
        }
    )
    return StreamingResponse(
        _range_stream(path, start, end),
        status_code=206,
        media_type=video.content_type,
        headers=headers,
    )

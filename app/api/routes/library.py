"""统一媒体库、个人/团队分组和媒体库概览接口。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...models import Image, MediaGroup, MediaGroupItem, User
from ...schemas import (
    LibraryStats,
    MediaGroupCreate,
    MediaGroupItemsAdd,
    MediaGroupItemsResult,
    MediaGroupListResponse,
    MediaGroupOut,
    MediaGroupUpdate,
    UnifiedMediaListResponse,
)
from ...services.library import (
    delete_group,
    ensure_unique_group_name,
    fresh_library_user,
    group_out,
    groups_out,
    library_stats,
    list_unified_media,
    serialized_library_lifecycle,
    validate_team_scope,
    visible_group_or_404,
)
from ...models.base import utcnow
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/api", tags=["media-library"])


def _resolve_group_media(
    db: Session,
    raw_codes: list[str],
    *,
    owner_id: int,
    team_id: int | None,
) -> tuple[list[Image], int]:
    """Normalize and fully validate one atomic add request under the lease."""
    codes: list[str] = []
    seen: set[str] = set()
    for raw_code in raw_codes:
        code = raw_code.strip()
        if not code or len(code) > 32:
            raise HTTPException(status_code=422, detail="invalid media code")
        if code not in seen:
            seen.add(code)
            codes.append(code)

    if not codes:
        return [], len(raw_codes)
    media_by_code = {
        media.code: media
        for media in db.execute(
            select(Image).where(
                Image.code.in_(codes), Image.media_kind.in_(("image", "video"))
            )
        ).scalars().all()
    }
    for code in codes:
        media = media_by_code.get(code)
        in_scope = bool(
            media is not None
            and (
                (team_id is None and media.owner_id == owner_id and media.team_id is None)
                or (team_id is not None and media.team_id == team_id)
            )
        )
        if not in_scope:
            # Do not reveal whether another user's/team's code exists.
            raise HTTPException(status_code=404, detail="media not found")
    return [media_by_code[code] for code in codes], len(raw_codes) - len(codes)


@router.get(
    "/library/stats",
    response_model=LibraryStats,
    summary="Current media-library overview",
)
def get_library_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LibraryStats:
    """普通用户返回个人空间口径；全局管理员返回全库口径。"""
    return library_stats(db, current_user)


@router.get(
    "/media",
    response_model=UnifiedMediaListResponse,
    summary="Unified image and video listing",
)
@serialized_library_lifecycle
def list_media(
    request: Request,
    current_user: User = Depends(get_current_user),
    team_id: int | None = Query(default=None, ge=1),
    group_id: int | None = Query(default=None, ge=1),
    kind: str = Query(default="all"),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> UnifiedMediaListResponse:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    return list_unified_media(
        db,
        request,
        current_user,
        team_id=team_id,
        group_id=group_id,
        kind=kind,
        query=q.strip(),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/media-groups",
    response_model=MediaGroupListResponse,
    summary="List personal or team media groups",
)
@serialized_library_lifecycle
def list_media_groups(
    current_user: User = Depends(get_current_user),
    team_id: int | None = Query(default=None, ge=1),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> MediaGroupListResponse:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    if team_id is None:
        filters = [
            MediaGroup.owner_id == current_user.id,
            MediaGroup.team_id.is_(None),
        ]
    else:
        validate_team_scope(db, team_id, current_user)
        filters = [MediaGroup.team_id == team_id]
    query = q.strip()
    if query:
        like = f"%{query}%"
        filters.append(or_(MediaGroup.name.like(like), MediaGroup.description.like(like)))

    total = db.scalar(select(func.count()).select_from(MediaGroup).where(*filters)) or 0
    rows = db.execute(
        select(MediaGroup)
        .where(*filters)
        .order_by(MediaGroup.sort_order.asc(), MediaGroup.updated_at.desc(), MediaGroup.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return MediaGroupListResponse(items=groups_out(db, rows), total=total)


@router.post(
    "/media-groups",
    response_model=MediaGroupOut,
    status_code=201,
    summary="Create a personal or team media group",
)
@serialized_library_lifecycle
def create_media_group(
    payload: MediaGroupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaGroupOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="media group name cannot be blank")
    if payload.team_id is not None:
        validate_team_scope(db, payload.team_id, current_user)
    ensure_unique_group_name(
        db,
        name=name,
        owner_id=current_user.id,
        team_id=payload.team_id,
    )
    media_rows, _duplicates = _resolve_group_media(
        db,
        payload.codes,
        owner_id=current_user.id,
        team_id=payload.team_id,
    )
    group = MediaGroup(
        owner_id=current_user.id,
        team_id=payload.team_id,
        name=name,
        description=payload.description.strip(),
        color=payload.color.lower(),
        sort_order=payload.sort_order,
    )
    db.add(group)
    db.flush()
    for media in media_rows:
        db.add(
            MediaGroupItem(
                group_id=group.id,
                media_id=media.id,
                added_by=current_user.id,
            )
        )
    db.commit()
    db.refresh(group)
    return group_out(db, group)


@router.get(
    "/media-groups/{group_id}",
    response_model=MediaGroupOut,
    summary="Media group detail",
)
@serialized_library_lifecycle
def get_media_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaGroupOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    return group_out(db, visible_group_or_404(db, group_id, current_user))


@router.patch(
    "/media-groups/{group_id}",
    response_model=MediaGroupOut,
    summary="Update a media group",
)
@serialized_library_lifecycle
def update_media_group(
    group_id: int,
    payload: MediaGroupUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaGroupOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    group = visible_group_or_404(db, group_id, current_user, manage=True)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        name = changes["name"].strip()
        if not name:
            raise HTTPException(status_code=422, detail="media group name cannot be blank")
        ensure_unique_group_name(
            db,
            name=name,
            owner_id=group.owner_id,
            team_id=group.team_id,
            exclude_id=group.id,
        )
        group.name = name
    if "description" in changes:
        group.description = changes["description"].strip()
    if "color" in changes:
        group.color = changes["color"].lower()
    if "sort_order" in changes:
        group.sort_order = changes["sort_order"]
    if changes:
        group.updated_at = utcnow()
        db.commit()
        db.refresh(group)
    return group_out(db, group)


@router.delete(
    "/media-groups/{group_id}",
    status_code=204,
    summary="Delete a media group without deleting its media",
)
@serialized_library_lifecycle
def remove_media_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    delete_group(db, visible_group_or_404(db, group_id, current_user, manage=True))


@router.get(
    "/media-groups/{group_id}/items",
    response_model=UnifiedMediaListResponse,
    summary="Search and paginate media in a group",
)
@serialized_library_lifecycle
def list_media_group_items(
    group_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    kind: str = Query(default="all"),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> UnifiedMediaListResponse:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    return list_unified_media(
        db,
        request,
        current_user,
        team_id=None,
        group_id=group_id,
        kind=kind,
        query=q.strip(),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/media-groups/{group_id}/items",
    response_model=MediaGroupItemsResult,
    summary="Add one or more media assets to a group",
)
@serialized_library_lifecycle
def add_media_group_items(
    group_id: int,
    payload: MediaGroupItemsAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaGroupItemsResult:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    group = visible_group_or_404(db, group_id, current_user, manage=True)
    media_rows, duplicate_count = _resolve_group_media(
        db,
        payload.codes,
        owner_id=group.owner_id,
        team_id=group.team_id,
    )
    media_ids = [media.id for media in media_rows]
    existing = set(
        db.execute(
            select(MediaGroupItem.media_id).where(
                MediaGroupItem.group_id == group.id,
                MediaGroupItem.media_id.in_(media_ids),
            )
        ).scalars()
    )
    added = 0
    for media_id in media_ids:
        if media_id in existing:
            continue
        db.add(
            MediaGroupItem(
                group_id=group.id,
                media_id=media_id,
                added_by=current_user.id,
            )
        )
        added += 1
    group.updated_at = utcnow()
    db.commit()
    db.refresh(group)
    return MediaGroupItemsResult(
        added=added,
        skipped=duplicate_count + len(media_ids) - added,
        group=group_out(db, group),
    )


@router.delete(
    "/media-groups/{group_id}/items/{code}",
    status_code=204,
    summary="Remove media from a group without deleting the asset",
)
@serialized_library_lifecycle
def remove_media_group_item(
    group_id: int,
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    group = visible_group_or_404(db, group_id, current_user, manage=True)
    item = db.execute(
        select(MediaGroupItem)
        .join(Image, Image.id == MediaGroupItem.media_id)
        .where(
            MediaGroupItem.group_id == group.id,
            Image.code == code,
            *(
                (Image.owner_id == group.owner_id, Image.team_id.is_(None))
                if group.team_id is None
                else (Image.team_id == group.team_id,)
            ),
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="media is not in this group")
    db.delete(item)
    group.updated_at = utcnow()
    db.commit()

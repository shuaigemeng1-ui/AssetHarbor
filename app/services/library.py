"""统一媒体库、媒体分组权限和显式生命周期管理。"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from functools import wraps

from fastapi import HTTPException, Request
from sqlalchemy import and_, delete, func, inspect as sa_inspect, or_, select, update
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models import Image, MediaGroup, MediaGroupItem, Team, TeamMember, UploadSession, User
from ..schemas import (
    LibraryStats,
    MediaGroupOut,
    UnifiedMediaInfo,
    UnifiedMediaListResponse,
)
from .signing import build_image_url, build_video_url
from .storage_quota import RESERVED_UPLOAD_STATUSES
from .teams import can_manage_team, get_membership

_MEDIA_KINDS = {"all", "image", "video"}
_library_lifecycle_lock = threading.RLock()


@contextmanager
def library_lifecycle_lease():
    """Serialize no-FK group changes with destructive media lifecycle work.

    The deployment is intentionally limited to one Python process/Uvicorn
    worker. Within that boundary this re-entrant lease closes check-then-write
    races without requiring unsupported SQLite row locks. Re-entrancy lets a
    user deletion invoke media/team deletion helpers under one lifecycle lease.
    """
    with _library_lifecycle_lock:
        yield


def serialized_library_lifecycle(func):
    """Decorator form used by synchronous FastAPI routes and services."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        with library_lifecycle_lease():
            return func(*args, **kwargs)

    return wrapped


def fresh_library_user(db: Session, user: User) -> User:
    """Revalidate an authenticated principal after waiting for the lease."""
    # ``db.rollback()`` expires ORM attributes. If another transaction deleted
    # the row while this request waited for the lease, reading ``user.id`` can
    # itself raise ObjectDeletedError. SQLAlchemy's identity key is immutable
    # session state and remains available without issuing a stale refresh.
    identity = sa_inspect(user).identity
    if not identity:
        raise HTTPException(status_code=401, detail="could not validate credentials")
    # ``Session.get`` is allowed to satisfy the lookup from the identity map.
    # Force a database round trip so a user deleted by another request while
    # this request waited outside the lifecycle lease cannot be reused.
    fresh = db.execute(
        select(User)
        .where(User.id == int(identity[0]))
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if fresh is None:
        raise HTTPException(status_code=401, detail="could not validate credentials")
    return fresh


def _valid_group_item_scope():
    """SQL condition that rejects stale/corrupted cross-space memberships."""
    return and_(
        Image.media_kind.in_(("image", "video")),
        or_(
            and_(
                MediaGroup.team_id.is_(None),
                Image.team_id.is_(None),
                Image.owner_id == MediaGroup.owner_id,
            ),
            and_(
                MediaGroup.team_id.is_not(None),
                Image.team_id == MediaGroup.team_id,
            ),
        ),
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="media group not found")


def can_view_group(db: Session, user: User, group: MediaGroup) -> bool:
    if user.role == "admin":
        return True
    if group.team_id is None:
        return group.owner_id == user.id
    return get_membership(db, group.team_id, user.id) is not None


def can_manage_group(db: Session, user: User, group: MediaGroup) -> bool:
    if user.role == "admin" or group.owner_id == user.id:
        return True
    return bool(
        group.team_id is not None
        and can_manage_team(db, group.team_id, user.id)
    )


def visible_group_or_404(
    db: Session, group_id: int, user: User, *, manage: bool = False
) -> MediaGroup:
    group = db.get(MediaGroup, group_id)
    if group is None or not can_view_group(db, user, group):
        raise _not_found()
    if group.team_id is not None and db.get(Team, group.team_id) is None:
        raise _not_found()
    if manage and not can_manage_group(db, user, group):
        raise HTTPException(status_code=403, detail="media group management privileges required")
    return group


def validate_team_scope(db: Session, team_id: int, user: User) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    if user.role != "admin" and get_membership(db, team_id, user.id) is None:
        raise HTTPException(status_code=404, detail="team not found")
    return team


def ensure_unique_group_name(
    db: Session,
    *,
    name: str,
    owner_id: int,
    team_id: int | None,
    exclude_id: int | None = None,
) -> None:
    filters = [func.lower(MediaGroup.name) == name.lower()]
    if team_id is None:
        filters.extend((MediaGroup.owner_id == owner_id, MediaGroup.team_id.is_(None)))
    else:
        filters.append(MediaGroup.team_id == team_id)
    if exclude_id is not None:
        filters.append(MediaGroup.id != exclude_id)
    if db.execute(select(MediaGroup.id).where(*filters)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="media group name already exists")


def group_out(db: Session, group: MediaGroup) -> MediaGroupOut:
    owner = db.get(User, group.owner_id)
    item_count = db.scalar(
        select(func.count())
        .select_from(MediaGroupItem)
        .join(Image, Image.id == MediaGroupItem.media_id)
        .join(MediaGroup, MediaGroup.id == MediaGroupItem.group_id)
        .where(MediaGroupItem.group_id == group.id, _valid_group_item_scope())
    ) or 0
    return MediaGroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        color=group.color,
        sort_order=group.sort_order,
        owner_id=group.owner_id,
        owner_username=owner.username if owner else None,
        team_id=group.team_id,
        item_count=item_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def groups_out(db: Session, groups: list[MediaGroup]) -> list[MediaGroupOut]:
    if not groups:
        return []
    owner_ids = {group.owner_id for group in groups}
    owners = dict(
        db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all()
    )
    group_ids = [group.id for group in groups]
    counts = dict(
        db.execute(
            select(MediaGroupItem.group_id, func.count())
            .join(Image, Image.id == MediaGroupItem.media_id)
            .join(MediaGroup, MediaGroup.id == MediaGroupItem.group_id)
            .where(MediaGroupItem.group_id.in_(group_ids), _valid_group_item_scope())
            .group_by(MediaGroupItem.group_id)
        ).all()
    )
    return [
        MediaGroupOut(
            id=group.id,
            name=group.name,
            description=group.description,
            color=group.color,
            sort_order=group.sort_order,
            owner_id=group.owner_id,
            owner_username=owners.get(group.owner_id),
            team_id=group.team_id,
            item_count=counts.get(group.id, 0),
            created_at=group.created_at,
            updated_at=group.updated_at,
        )
        for group in groups
    ]


def unified_media_out(
    request: Request, media: Image, owner_username: str | None = None
) -> UnifiedMediaInfo:
    url = (
        build_video_url(request, media.code)
        if media.media_kind == "video"
        else build_image_url(request, media.code)
    )
    return UnifiedMediaInfo(
        code=media.code,
        url=url,
        size=media.size,
        content_type=media.content_type,
        sha256=media.sha256,
        created_at=media.created_at,
        name=media.name,
        visibility=media.visibility,
        owner_id=media.owner_id,
        owner_username=owner_username,
        team_id=media.team_id,
        original_filename=media.original_filename,
        media_kind=media.media_kind,
    )


def list_unified_media(
    db: Session,
    request: Request,
    user: User,
    *,
    team_id: int | None,
    group_id: int | None,
    kind: str,
    query: str,
    limit: int,
    offset: int,
) -> UnifiedMediaListResponse:
    if kind not in _MEDIA_KINDS:
        raise HTTPException(status_code=422, detail="kind must be all, image or video")

    statement = select(Image)
    count_statement = select(func.count()).select_from(Image)
    filters = []
    order_columns = (Image.created_at.desc(), Image.id.desc())

    if group_id is not None:
        group = visible_group_or_404(db, group_id, user)
        if team_id is not None and group.team_id != team_id:
            raise HTTPException(status_code=422, detail="group does not belong to the requested scope")
        statement = statement.join(MediaGroupItem, MediaGroupItem.media_id == Image.id)
        count_statement = count_statement.join(
            MediaGroupItem, MediaGroupItem.media_id == Image.id
        )
        filters.append(MediaGroupItem.group_id == group.id)
        if group.team_id is None:
            filters.extend((Image.owner_id == group.owner_id, Image.team_id.is_(None)))
        else:
            filters.append(Image.team_id == group.team_id)
        order_columns = (MediaGroupItem.created_at.desc(), MediaGroupItem.id.desc())
    elif team_id is not None:
        validate_team_scope(db, team_id, user)
        filters.append(Image.team_id == team_id)
    elif user.role != "admin":
        filters.extend((Image.owner_id == user.id, Image.team_id.is_(None)))

    if kind != "all":
        filters.append(Image.media_kind == kind)
    else:
        filters.append(Image.media_kind.in_(("image", "video")))
    if query:
        like = f"%{query}%"
        filters.append(
            or_(Image.name.like(like), Image.original_filename.like(like), Image.code.like(like))
        )

    total = db.scalar(count_statement.where(*filters)) or 0
    media_rows = db.execute(
        statement.where(*filters).order_by(*order_columns).limit(limit).offset(offset)
    ).scalars().all()
    owner_ids = {media.owner_id for media in media_rows if media.owner_id is not None}
    owner_names = (
        dict(db.execute(select(User.id, User.username).where(User.id.in_(owner_ids))).all())
        if owner_ids
        else {}
    )
    return UnifiedMediaListResponse(
        items=[unified_media_out(request, media, owner_names.get(media.owner_id)) for media in media_rows],
        total=total,
    )


def delete_group(db: Session, group: MediaGroup, *, commit: bool = True) -> None:
    db.execute(delete(MediaGroupItem).where(MediaGroupItem.group_id == group.id))
    db.delete(group)
    if commit:
        db.commit()


def delete_group_items_for_media(db: Session, media_id: int) -> None:
    """在删除资产行前显式清除所有多对多记录。"""
    db.execute(delete(MediaGroupItem).where(MediaGroupItem.media_id == media_id))


def delete_team_groups(db: Session, team_id: int) -> None:
    """团队解散时删除共享分组；媒体本身由现有逻辑退回上传者。"""
    group_ids = list(
        db.execute(select(MediaGroup.id).where(MediaGroup.team_id == team_id)).scalars()
    )
    if group_ids:
        db.execute(delete(MediaGroupItem).where(MediaGroupItem.group_id.in_(group_ids)))
        db.execute(delete(MediaGroup).where(MediaGroup.id.in_(group_ids)))


def prepare_groups_for_user_deletion(db: Session, user_id: int) -> None:
    """删除个人分组，并把仍存续团队中的共享分组交给团队所有者。"""
    personal_ids = list(
        db.execute(
            select(MediaGroup.id).where(
                MediaGroup.owner_id == user_id, MediaGroup.team_id.is_(None)
            )
        ).scalars()
    )
    if personal_ids:
        db.execute(delete(MediaGroupItem).where(MediaGroupItem.group_id.in_(personal_ids)))
        db.execute(delete(MediaGroup).where(MediaGroup.id.in_(personal_ids)))

    shared = db.execute(
        select(MediaGroup).where(
            MediaGroup.owner_id == user_id, MediaGroup.team_id.is_not(None)
        )
    ).scalars().all()
    for group in shared:
        team = db.get(Team, group.team_id)
        if team is None:
            delete_group(db, group, commit=False)
        elif team.owner_id != user_id:
            group.owner_id = team.owner_id

    # Retained group items must not keep a dangling audit user id. Personal
    # groups were removed above; shared groups now have a valid owner to use as
    # the lifecycle successor.
    db.flush()
    retained_items = db.execute(
        select(MediaGroupItem, MediaGroup.owner_id)
        .join(MediaGroup, MediaGroup.id == MediaGroupItem.group_id)
        .where(MediaGroupItem.added_by == user_id)
    ).all()
    for item, successor_id in retained_items:
        item.added_by = successor_id


def transfer_member_groups(db: Session, team: Team, user_id: int) -> None:
    """成员被移出团队时，避免其创建的共享分组成为不可管理的孤儿。"""
    db.execute(
        update(MediaGroup)
        .where(MediaGroup.team_id == team.id, MediaGroup.owner_id == user_id)
        .values(owner_id=team.owner_id)
    )


def cleanup_orphan_media_library() -> int:
    """Repair no-FK media-library metadata after crashes/manual DB changes.

    Missing-scope groups are removed, missing audit users are replaced with a
    valid group owner, and missing or cross-scope media memberships are
    deleted. The function is safe and idempotent and is called at startup.
    """
    removed = 0
    with library_lifecycle_lease():
        with SessionLocal() as db:
            db.rollback()
            groups = db.execute(select(MediaGroup)).scalars().all()
            for group in groups:
                owner = db.get(User, group.owner_id)
                if group.team_id is None:
                    if owner is None:
                        delete_group(db, group, commit=False)
                        removed += 1
                    continue

                team = db.get(Team, group.team_id)
                team_owner = db.get(User, team.owner_id) if team is not None else None
                if team is None or team_owner is None:
                    delete_group(db, group, commit=False)
                    removed += 1
                elif owner is None or (
                    owner.role != "admin"
                    and get_membership(db, team.id, owner.id) is None
                ):
                    group.owner_id = team.owner_id

            db.flush()
            items = db.execute(select(MediaGroupItem)).scalars().all()
            for item in items:
                group = db.get(MediaGroup, item.group_id)
                media = db.get(Image, item.media_id)
                valid_scope = bool(
                    group is not None
                    and media is not None
                    and media.media_kind in ("image", "video")
                    and (
                        (
                            group.team_id is None
                            and media.team_id is None
                            and media.owner_id == group.owner_id
                        )
                        or (
                            group.team_id is not None
                            and media.team_id == group.team_id
                        )
                    )
                )
                if not valid_scope:
                    db.delete(item)
                    removed += 1
                elif db.get(User, item.added_by) is None:
                    item.added_by = group.owner_id
            db.commit()
    return removed


def library_stats(db: Session, user: User) -> LibraryStats:
    if user.role == "admin":
        media_scope = []
        upload_scope = []
        group_scope = []
        teams_count = db.scalar(select(func.count()).select_from(Team)) or 0
        scope = "global"
    else:
        media_scope = [Image.owner_id == user.id, Image.team_id.is_(None)]
        upload_scope = [UploadSession.owner_id == user.id, UploadSession.team_id.is_(None)]
        group_scope = [MediaGroup.owner_id == user.id, MediaGroup.team_id.is_(None)]
        teams_count = db.scalar(
            select(func.count()).select_from(TeamMember).where(TeamMember.user_id == user.id)
        ) or 0
        scope = "personal"

    images = db.scalar(
        select(func.count()).select_from(Image).where(*media_scope, Image.media_kind == "image")
    ) or 0
    videos = db.scalar(
        select(func.count()).select_from(Image).where(*media_scope, Image.media_kind == "video")
    ) or 0
    storage_bytes = db.scalar(
        select(func.coalesce(func.sum(Image.size), 0)).where(*media_scope)
    ) or 0
    pending_upload_bytes = db.scalar(
        select(func.coalesce(func.sum(UploadSession.size), 0)).where(
            *upload_scope,
            UploadSession.status.in_(RESERVED_UPLOAD_STATUSES),
        )
    ) or 0
    groups = db.scalar(
        select(func.count()).select_from(MediaGroup).where(*group_scope)
    ) or 0
    return LibraryStats(
        scope=scope,
        images=images,
        videos=videos,
        media_total=images + videos,
        storage_bytes=storage_bytes,
        pending_upload_bytes=pending_upload_bytes,
        groups=groups,
        teams_count=teams_count,
    )

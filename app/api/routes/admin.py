"""Admin-only endpoints: stats, traffic/storage, user management, team overview."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models import ApiKey, Image, Team, TeamMember, TrafficDaily, UploadSession, User
from ...schemas import (
    AdminStats,
    AdminTrafficStats,
    AdminUserCreate,
    MemberUsagePoint,
    ResetPasswordRequest,
    RoleUpdate,
    TeamAdminOut,
    TrafficApiKeyPoint,
    TrafficDailyPoint,
    TrafficRoutePoint,
    TrafficTotals,
    UserOut,
)
from ...core.security import hash_password
from ...services.images import delete_image
from ...services.identifiers import next_team_member_id, next_user_id
from ...services.library import (
    fresh_library_user,
    library_lifecycle_lease,
    prepare_groups_for_user_deletion,
    serialized_library_lifecycle,
)
from ...services.storage_quota import RESERVED_UPLOAD_STATUSES
from ...services.traffic import flush_traffic, telemetry_integrity_status
from ...services.videos import delete_upload_sessions_for_owner
from ..deps import get_db, require_jwt_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_jwt_admin)])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


def _traffic_totals(row) -> TrafficTotals:
    """Normalize SQL aggregate rows and expose total transfer bytes."""
    request_count, error_count, request_bytes, response_bytes = (int(value or 0) for value in row)
    return TrafficTotals(
        request_count=request_count,
        error_count=error_count,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        total_bytes=request_bytes + response_bytes,
    )


def _traffic_sum_columns():
    return (
        func.coalesce(func.sum(TrafficDaily.request_count), 0),
        func.coalesce(func.sum(TrafficDaily.error_count), 0),
        func.coalesce(func.sum(TrafficDaily.request_bytes), 0),
        func.coalesce(func.sum(TrafficDaily.response_bytes), 0),
    )


def _flush_traffic_or_503() -> None:
    """Never present a silently stale management traffic snapshot."""
    if not flush_traffic():
        raise HTTPException(
            status_code=503,
            detail="traffic statistics are temporarily unavailable",
        )


@router.post("/users", response_model=UserOut, status_code=201, summary="Create a user (admin)")
def create_user(
    payload: AdminUserCreate,
    current_user: User = Depends(require_jwt_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'user'")
    # Bcrypt is intentionally outside the global lifecycle lease. Authorization
    # and the owner-scoped insert are revalidated atomically after that work.
    password_hash = hash_password(payload.password)
    with library_lifecycle_lease():
        db.rollback()
        current_user = fresh_library_user(db, current_user)
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="admin privileges required")
        if db.execute(
            select(User.id).where(User.username == payload.username)
        ).scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="username already taken")
        user = User(
            id=next_user_id(db),
            username=payload.username,
            password_hash=password_hash,
            role=payload.role,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="username already taken")
        db.refresh(user)
        return _user_out(user)


@router.get("/stats", response_model=AdminStats, summary="System statistics (admin)")
def admin_stats(
    current_user: User = Depends(require_jwt_admin),
    db: Session = Depends(get_db),
) -> AdminStats:
    # The admin view should reflect all requests completed before this one.
    # A short telemetry-only barrier never affects normal API hot paths.
    _flush_traffic_or_503()
    telemetry_complete, telemetry_dropped_events = telemetry_integrity_status()
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin privileges required")
    users = db.scalar(select(func.count()).select_from(User)) or 0
    images = db.scalar(
        select(func.count()).select_from(Image).where(Image.media_kind == "image")
    ) or 0
    videos = db.scalar(
        select(func.count()).select_from(Image).where(Image.media_kind == "video")
    ) or 0
    teams = db.scalar(select(func.count()).select_from(Team)) or 0
    storage = db.scalar(select(func.coalesce(func.sum(Image.size), 0))) or 0
    pending_upload_bytes = db.scalar(
        select(func.coalesce(func.sum(UploadSession.size), 0)).where(
            UploadSession.status.in_(RESERVED_UPLOAD_STATUSES),
            UploadSession.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        )
    ) or 0
    traffic = _traffic_totals(db.execute(select(*_traffic_sum_columns())).one())
    return AdminStats(
        users=users,
        images=images,
        videos=videos,
        media_total=images + videos,
        teams=teams,
        storage_bytes=storage,
        pending_upload_bytes=pending_upload_bytes,
        traffic_request_count=traffic.request_count,
        traffic_request_bytes=traffic.request_bytes,
        traffic_response_bytes=traffic.response_bytes,
        traffic_total_bytes=traffic.total_bytes,
        telemetry_complete=telemetry_complete,
        telemetry_dropped_events=telemetry_dropped_events,
    )


@router.get(
    "/traffic-stats",
    response_model=AdminTrafficStats,
    summary="API-key traffic trends and per-member storage usage (admin)",
)
def admin_traffic_stats(
    days: int = Query(default=7, ge=1, le=365, description="UTC calendar days, including today"),
    current_user: User = Depends(require_jwt_admin),
    db: Session = Depends(get_db),
) -> AdminTrafficStats:
    """Return API-key traffic trends and every member's storage usage."""
    _flush_traffic_or_503()
    telemetry_complete, telemetry_dropped_events = telemetry_integrity_status()
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin privileges required")
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days - 1)
    period_filter = TrafficDaily.day >= start_date
    api_key_period_filter = (period_filter, TrafficDaily.api_key_id > 0)

    summary = _traffic_totals(
        db.execute(select(*_traffic_sum_columns()).where(*api_key_period_filter)).one()
    )
    anonymous = _traffic_totals(
        db.execute(
            select(*_traffic_sum_columns()).where(period_filter, TrafficDaily.user_id == 0)
        ).one()
    )

    daily_rows = {
        day: _traffic_totals((count, errors, request_bytes, response_bytes))
        for day, count, errors, request_bytes, response_bytes in db.execute(
            select(TrafficDaily.day, *_traffic_sum_columns())
            .where(*api_key_period_filter)
            .group_by(TrafficDaily.day)
            .order_by(TrafficDaily.day)
        ).all()
    }
    daily: list[TrafficDailyPoint] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        totals = daily_rows.get(day, TrafficTotals(
            request_count=0, error_count=0, request_bytes=0, response_bytes=0, total_bytes=0
        ))
        daily.append(TrafficDailyPoint(date=day, **totals.model_dump()))

    routes = [
        TrafficRoutePoint(
            route=route,
            method=method,
            **_traffic_totals((count, errors, request_bytes, response_bytes)).model_dump(),
        )
        for route, method, count, errors, request_bytes, response_bytes in db.execute(
            select(TrafficDaily.route, TrafficDaily.method, *_traffic_sum_columns())
            .where(*api_key_period_filter)
            .group_by(TrafficDaily.route, TrafficDaily.method)
            .order_by(func.sum(TrafficDaily.request_count).desc(), TrafficDaily.route)
            .limit(200)
        ).all()
    ]

    api_key_rows = db.execute(
        select(
            TrafficDaily.api_key_id,
            TrafficDaily.user_id,
            *_traffic_sum_columns(),
        )
        .where(*api_key_period_filter)
        .group_by(TrafficDaily.api_key_id, TrafficDaily.user_id)
        .order_by(func.sum(TrafficDaily.request_count).desc())
        .limit(200)
    ).all()
    key_ids = {row[0] for row in api_key_rows}
    key_info = {
        key.id: key
        for key in db.execute(select(ApiKey).where(ApiKey.id.in_(key_ids))).scalars().all()
    } if key_ids else {}
    api_user_ids = {row[1] for row in api_key_rows}
    api_usernames = dict(
        db.execute(select(User.id, User.username).where(User.id.in_(api_user_ids))).all()
    ) if api_user_ids else {}
    api_keys = []
    for key_id, user_id, count, errors, request_bytes, response_bytes in api_key_rows:
        key = key_info.get(key_id)
        api_keys.append(
            TrafficApiKeyPoint(
                api_key_id=key_id,
                key_name=key.name if key else None,
                key_prefix=key.key_prefix if key else None,
                user_id=user_id,
                username=api_usernames.get(user_id),
                **_traffic_totals((count, errors, request_bytes, response_bytes)).model_dump(),
            )
        )

    member_traffic = {
        user_id: _traffic_totals((count, errors, request_bytes, response_bytes))
        for user_id, count, errors, request_bytes, response_bytes in db.execute(
            select(TrafficDaily.user_id, *_traffic_sum_columns())
            .where(*api_key_period_filter, TrafficDaily.user_id > 0)
            .group_by(TrafficDaily.user_id)
        ).all()
    }
    media_usage: dict[int, dict[str, int]] = {}
    for owner_id, media_kind, size in db.execute(
        select(Image.owner_id, Image.media_kind, func.coalesce(func.sum(Image.size), 0))
        .where(Image.owner_id.is_not(None))
        .group_by(Image.owner_id, Image.media_kind)
    ).all():
        media_usage.setdefault(owner_id, {})[media_kind] = int(size or 0)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    pending_usage = dict(
        db.execute(
            select(UploadSession.owner_id, func.coalesce(func.sum(UploadSession.size), 0))
            .where(
                UploadSession.status.in_(RESERVED_UPLOAD_STATUSES),
                UploadSession.expires_at > now,
            )
            .group_by(UploadSession.owner_id)
        ).all()
    )
    zero = TrafficTotals(
        request_count=0, error_count=0, request_bytes=0, response_bytes=0, total_bytes=0
    )
    members: list[MemberUsagePoint] = []
    for user in db.execute(select(User).order_by(User.username, User.id)).scalars().all():
        kinds = media_usage.get(user.id, {})
        image_bytes = int(kinds.get("image", 0))
        video_bytes = int(kinds.get("video", 0))
        storage_bytes = image_bytes + video_bytes
        pending_bytes = int(pending_usage.get(user.id, 0) or 0)
        members.append(
            MemberUsagePoint(
                user_id=user.id,
                username=user.username,
                role=user.role,
                storage_bytes=storage_bytes,
                image_bytes=image_bytes,
                video_bytes=video_bytes,
                pending_upload_bytes=pending_bytes,
                total_usage_bytes=storage_bytes + pending_bytes,
                **member_traffic.get(user.id, zero).model_dump(),
            )
        )

    return AdminTrafficStats(
        telemetry_complete=telemetry_complete,
        telemetry_dropped_events=telemetry_dropped_events,
        days=days,
        start_date=start_date,
        end_date=end_date,
        summary=summary,
        anonymous=anonymous,
        daily=daily,
        routes=routes,
        api_keys=api_keys,
        members=members,
    )


@router.get("/teams", response_model=list[TeamAdminOut], summary="All teams with member counts (admin)")
def admin_teams(db: Session = Depends(get_db)) -> list[TeamAdminOut]:
    rows = db.execute(
        select(Team, User.username).join(User, User.id == Team.owner_id).order_by(Team.id)
    ).all()
    if not rows:
        return []
    team_ids = [team.id for team, _ in rows]
    counts = dict(
        db.execute(
            select(TeamMember.team_id, func.count())
            .where(TeamMember.team_id.in_(team_ids))
            .group_by(TeamMember.team_id)
        ).all()
    )
    return [
        TeamAdminOut(
            id=team.id,
            name=team.name,
            description=team.description,
            owner_username=owner_name,
            member_count=counts.get(team.id, 0),
            created_at=team.created_at,
        )
        for team, owner_name in rows
    ]


@router.patch("/users/{user_id}/role", response_model=UserOut, summary="Set a user's global role (admin)")
@serialized_library_lifecycle
def set_user_role(
    user_id: int,
    payload: RoleUpdate,
    current_user: User = Depends(require_jwt_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin privileges required")
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'user'")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot change your own role")

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")

    if target.role != payload.role:
        # Role and JWT revocation are one atomic statement. The SQL-side
        # increment preserves a concurrent password-reset increment too.
        db.execute(
            update(User)
            .where(User.id == target.id)
            .values(role=payload.role, auth_version=User.auth_version + 1)
            .execution_options(synchronize_session=False)
        )
    db.commit()
    db.expire_all()
    target = db.get(User, user_id)
    return _user_out(target)


@router.patch("/users/{user_id}/password", status_code=204, summary="Reset a user's password (admin)")
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    current_user: User = Depends(require_jwt_admin),
    db: Session = Depends(get_db),
) -> None:
    # Bcrypt is intentionally outside the global lifecycle lease, matching
    # create_user: a ~100ms+ hash must not serialize every media upload or
    # deletion behind one password reset. Only the short revalidation and the
    # credential UPDATE run under the lease.
    password_hash = hash_password(payload.new_password)
    with library_lifecycle_lease():
        # Dependency authorization may be stale after waiting for the lifecycle
        # lease. Reopen the transaction and re-check the administrator before
        # the credential write, matching destructive admin operations.
        db.rollback()
        current_user = fresh_library_user(db, current_user)
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="admin privileges required")
        target = db.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="user not found")
        db.execute(
            update(User)
            .where(User.id == target.id)
            .values(
                password_hash=password_hash,
                auth_version=User.auth_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()


@router.delete("/users/{user_id}", status_code=204, summary="Delete a user and all their data (admin)")
@serialized_library_lifecycle
def delete_user(
    user_id: int,
    current_user: User = Depends(require_jwt_admin),
    db: Session = Depends(get_db),
) -> None:
    # Fresh transaction after entering the no-FK lifecycle lease.
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin privileges required")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")

    # --- Team assets are preserved and transferred to the team. ---
    # Account deletion never deletes team media/upload sessions.  Teams owned
    # by the target are transferred to another member (preferring an admin),
    # or to the deleting administrator as a last resort so no team is orphaned.
    owned_teams = db.execute(select(Team).where(Team.owner_id == target.id)).scalars().all()
    for team in owned_teams:
        successors = db.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team.id, TeamMember.user_id != target.id)
            .order_by(TeamMember.role.desc(), TeamMember.id.asc())
        ).scalars().all()
        successor = (
            next((m for m in successors if m.role == "admin"), None)
            or (successors[0] if successors else None)
        )
        successor_membership = successor
        successor_user = db.get(User, successor.user_id) if successor is not None else current_user
        team.owner_id = successor_user.id
        if successor_membership is None:
            existing = db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team.id,
                    TeamMember.user_id == successor_user.id,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    TeamMember(
                        id=next_team_member_id(db),
                        team_id=team.id,
                        user_id=successor_user.id,
                        role="owner",
                    )
                )
            else:
                existing.role = "owner"
        else:
            successor_membership.role = "owner"

    # Transfer every remaining team asset uploaded by the target to the final
    # team owner (handles both teams the target owned and teams they merely
    # belonged to).  Pending upload sessions are transferred, not cancelled.
    for membership in db.execute(
        select(TeamMember).where(TeamMember.user_id == target.id)
    ).scalars().all():
        team = db.get(Team, membership.team_id)
        if team is None:
            continue
        db.execute(
            update(Image)
            .where(Image.team_id == team.id, Image.owner_id == target.id)
            .values(owner_id=team.owner_id)
        )
        db.execute(
            update(UploadSession)
            .where(UploadSession.team_id == team.id, UploadSession.owner_id == target.id)
            .values(owner_id=team.owner_id)
        )

    # Persist the ownership transfer before the personal-session cleanup:
    # cancel_upload_session_internal() begins with a defensive rollback, which
    # would otherwise discard the team/session owner changes staged above.
    db.commit()

    # Sessions have no database foreign keys and are cleaned explicitly,
    # including their on-disk temporary chunks.  Only personal (non-team)
    # sessions are removed; team sessions were transferred above.
    delete_upload_sessions_for_owner(db, target.id)

    # New media-library tables intentionally have no foreign keys, so their
    # owner/item lifecycle is maintained explicitly before deleting assets.
    prepare_groups_for_user_deletion(db, target.id)
    # Persist group cleanup/transfers first so an image-less team owner cannot
    # leave orphan personal or shared groups behind.
    db.commit()

    # Only personal media are deleted with the account; team media remain.
    for image in db.execute(
        select(Image).where(Image.owner_id == target.id, Image.team_id.is_(None))
    ).scalars().all():
        delete_image(db, image)

    # Memberships in other teams, API keys, then the account itself.
    db.execute(delete(TeamMember).where(TeamMember.user_id == target.id))
    db.execute(delete(ApiKey).where(ApiKey.user_id == target.id))
    # Traffic aggregates intentionally have no FK; account deletion therefore
    # removes its history explicitly (including rows attributed to its keys).
    db.execute(delete(TrafficDaily).where(TrafficDaily.user_id == target.id))
    db.delete(target)
    db.commit()

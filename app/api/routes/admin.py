"""Admin-only endpoints: stats, user management, team overview."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models import ApiKey, Image, Team, TeamMember, UploadSession, User
from ...schemas import (
    AdminStats,
    AdminUserCreate,
    ResetPasswordRequest,
    RoleUpdate,
    TeamAdminOut,
    UserOut,
)
from ...core.security import hash_password
from ...services.images import delete_image
from ...services.library import (
    fresh_library_user,
    library_lifecycle_lease,
    prepare_groups_for_user_deletion,
    serialized_library_lifecycle,
)
from ...services.storage_quota import RESERVED_UPLOAD_STATUSES
from ...services.videos import delete_upload_sessions_for_owner, dissolve_team_media
from ..deps import get_db, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.post("/users", response_model=UserOut, status_code=201, summary="Create a user (admin)")
def create_user(
    payload: AdminUserCreate,
    current_user: User = Depends(require_admin),
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
def admin_stats(db: Session = Depends(get_db)) -> AdminStats:
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
            UploadSession.status.in_(RESERVED_UPLOAD_STATUSES)
        )
    ) or 0
    return AdminStats(
        users=users,
        images=images,
        videos=videos,
        media_total=images + videos,
        teams=teams,
        storage_bytes=storage,
        pending_upload_bytes=pending_upload_bytes,
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
    current_user: User = Depends(require_admin),
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
@serialized_library_lifecycle
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    # Dependency authorization may be stale after waiting for the lifecycle
    # lease. Reopen the transaction and re-check the administrator before the
    # credential write, matching destructive admin operations.
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
            password_hash=hash_password(payload.new_password),
            auth_version=User.auth_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()


@router.delete("/users/{user_id}", status_code=204, summary="Delete a user and all their data (admin)")
@serialized_library_lifecycle
def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
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

    # Sessions have no database foreign keys and are cleaned explicitly,
    # including their on-disk temporary chunks. Cancellation intentionally
    # starts with rollback for PUT-race safety, so this must happen before
    # staging any other lifecycle changes in this transaction.
    delete_upload_sessions_for_owner(db, target.id)

    # New media-library tables intentionally have no foreign keys, so their
    # owner/item lifecycle is maintained explicitly before deleting assets.
    prepare_groups_for_user_deletion(db, target.id)
    # Team dissolution also begins with a defensive rollback. Persist group
    # cleanup/transfers first so an image-less team owner cannot leave orphan
    # personal or shared groups behind.
    db.commit()

    # Images (rows + files on disk).
    for image in db.execute(select(Image).where(Image.owner_id == target.id)).scalars().all():
        delete_image(db, image)

    # Teams owned by the user (their team-space images return to their owners).
    for team in db.execute(select(Team).where(Team.owner_id == target.id)).scalars().all():
        dissolve_team_media(db, team)

    # Memberships in other teams, API keys, then the account itself.
    db.execute(delete(TeamMember).where(TeamMember.user_id == target.id))
    db.execute(delete(ApiKey).where(ApiKey.user_id == target.id))
    db.delete(target)
    db.commit()

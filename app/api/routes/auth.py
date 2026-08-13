"""Authentication: register, login, current user, change password."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.security import (
    create_access_token,
    hash_password,
    password_hash_needs_upgrade,
    verify_login_password,
    verify_password,
)
from ...models import User
from ...schemas import ChangePasswordRequest, PublicConfig, RegisterRequest, TokenResponse, UserOut
from ...services.ratelimit import check_rate_limit, client_ip
from ...services.identifiers import next_user_id
from ...services.library import library_lifecycle_lease
from ..deps import get_current_user, get_db, require_jwt_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.get("/config", response_model=PublicConfig, summary="Public client configuration")
def public_config() -> PublicConfig:
    return PublicConfig(
        version=settings.version,
        registration_mode=settings.allow_registration,
        max_upload_size_mb=settings.max_upload_size_mb,
        max_video_size_mb=settings.max_video_size_mb,
        video_chunk_size_mb=settings.video_chunk_size_mb,
        max_active_video_uploads=settings.max_active_video_uploads,
        video_chunk_concurrency=settings.video_chunk_concurrency,
        user_storage_quota_bytes=settings.user_storage_quota_bytes,
        team_storage_quota_bytes=settings.team_storage_quota_bytes,
    )


@router.post("/register", response_model=UserOut, status_code=201, summary="Register a new user")
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> UserOut:
    # Registration creates durable accounts and therefore needs its own
    # throttle instead of borrowing the login limiter.
    check_rate_limit(
        f"register-ip:{client_ip(request)}",
        settings.registration_rate_limit_per_minute,
        60,
    )
    check_rate_limit(
        f"register-user:{payload.username.lower()}",
        settings.registration_rate_limit_per_username,
        60,
    )
    mode = settings.allow_registration
    if mode == "closed":
        raise HTTPException(status_code=403, detail="registration is disabled")
    if mode == "invite":
        if not payload.invite_code or not settings.invite_code or not secrets.compare_digest(
            payload.invite_code,
            settings.invite_code,
        ):
            raise HTTPException(status_code=403, detail="invalid invite code")

    password_hash = hash_password(payload.password)
    with library_lifecycle_lease():
        db.rollback()
        exists = db.execute(
            select(User).where(User.username == payload.username)
        ).scalar_one_or_none()
        if exists is not None:
            raise HTTPException(status_code=409, detail="username already taken")

        user = User(
            id=next_user_id(db),
            username=payload.username,
            password_hash=password_hash,
            role="user",
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="username already taken")
        db.refresh(user)
        return _user_out(user)


@router.post("/login", response_model=TokenResponse, summary="Login and get a JWT access token")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Anti brute-force: throttle per IP and per account.
    check_rate_limit(f"login-ip:{client_ip(request)}", settings.login_rate_limit_per_minute, 60)
    if len(form.username) > 64 or len(form.password) > 128:
        # Avoid unbounded rate-limit keys and password hashing work. The same
        # generic response keeps account existence undisclosed.
        raise HTTPException(status_code=401, detail="incorrect username or password")
    check_rate_limit(f"login-user:{form.username}", settings.login_rate_limit_per_username, 60)

    user = db.execute(select(User).where(User.username == form.username)).scalar_one_or_none()
    original_hash = user.password_hash if user is not None else None
    if not verify_login_password(form.password, original_hash):
        raise HTTPException(status_code=401, detail="incorrect username or password")

    # Transparently migrate pre bcrypt-SHA256 accounts after their first
    # successful login. The compare-and-swap is essential: if an administrator
    # or the user changes the password after verification, an old-password
    # login must never overwrite the newer credential or receive a token.
    if password_hash_needs_upgrade(original_hash):
        original_version = user.auth_version
        result = db.execute(
            update(User)
            .where(
                User.id == user.id,
                User.password_hash == original_hash,
                User.auth_version == original_version,
            )
            .values(password_hash=hash_password(form.password))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=401, detail="incorrect username or password")
        db.commit()
        db.refresh(user)
    return TokenResponse(access_token=create_access_token(user), user=_user_out(user))


@router.get("/me", response_model=UserOut, summary="Get the current user")
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(current_user)


@router.post("/change-password", status_code=204, summary="Change your password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(require_jwt_user),
    db: Session = Depends(get_db),
) -> None:
    original_hash = current_user.password_hash
    original_version = current_user.auth_version
    if not verify_password(payload.old_password, original_hash):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    if payload.new_password == payload.old_password:
        raise HTTPException(status_code=400, detail="new password must differ from the current one")

    # Password and revocation version change in one conditional UPDATE. A
    # concurrent admin reset, role change, or second password change makes the
    # stale request fail instead of overwriting the winning credential.
    result = db.execute(
        update(User)
        .where(
            User.id == current_user.id,
            User.password_hash == original_hash,
            User.auth_version == original_version,
        )
        .values(
            password_hash=hash_password(payload.new_password),
            auth_version=User.auth_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="credentials changed concurrently; sign in again",
        )
    db.commit()

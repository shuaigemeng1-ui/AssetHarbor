"""Authentication: register, login, current user, change password."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from ...models import User
from ...schemas import ChangePasswordRequest, PublicConfig, RegisterRequest, TokenResponse, UserOut
from ...services.ratelimit import check_rate_limit, client_ip
from ..deps import get_current_user, get_db

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
        default_visibility=settings.default_visibility,
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

    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="username already taken")

    user = User(username=payload.username, password_hash=hash_password(payload.password), role="user")
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
    check_rate_limit(f"login-user:{form.username}", settings.login_rate_limit_per_username, 60)

    user = db.execute(select(User).where(User.username == form.username)).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="incorrect username or password")
    return TokenResponse(access_token=create_access_token(user), user=_user_out(user))


@router.get("/me", response_model=UserOut, summary="Get the current user")
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(current_user)


@router.post("/change-password", status_code=204, summary="Change your password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    if payload.new_password == payload.old_password:
        raise HTTPException(status_code=400, detail="new password must differ from the current one")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()

"""Authentication: register, login, current user."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services.ratelimit import check_rate_limit, client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.post("/register", response_model=UserOut, status_code=201, summary="Register a new user")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    mode = settings.allow_registration
    if mode == "closed":
        raise HTTPException(status_code=403, detail="registration is disabled")
    if mode == "invite":
        if not payload.invite_code or payload.invite_code != settings.invite_code:
            raise HTTPException(status_code=403, detail="invalid invite code")

    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="username already taken")

    user = User(username=payload.username, password_hash=hash_password(payload.password), role="user")
    db.add(user)
    db.commit()
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

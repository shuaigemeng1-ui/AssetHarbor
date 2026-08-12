"""Password hashing, JWT + API-key authentication and auth dependencies.

Authentication accepts either a JWT access token or a per-user API key,
sent as ``Authorization: Bearer <token>`` or (for API keys) ``X-API-Key: <key>``.
API keys are stored only as SHA-256 hashes — the plaintext is shown exactly
once at creation and cannot be recovered afterwards.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApiKey, User
from .config import settings
from .database import SessionLocal, get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Ephemeral secret when the operator did not configure OSS_JWT_SECRET
# (tokens are then invalidated on every restart — see README).
_JWT_SECRET = settings.jwt_secret or secrets.token_urlsafe(48)
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_expire_minutes),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def _user_from_payload(payload: dict, db: Session) -> User | None:
    user_id = payload.get("sub")
    if user_id is None:
        return None
    try:
        return db.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def generate_api_key() -> str:
    """256-bit random, URL-safe — collision-free in practice."""
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _authenticate(request: Request, bearer: str | None, db: Session) -> User | None:
    """Resolve a request to a user via JWT or API key.

    Order: Authorization: Bearer is tried as JWT first, then as an API key;
    a separate ``X-API-Key`` header is accepted as an API key too.
    """
    candidates: list[str] = []
    if bearer:
        candidates.append(bearer)
    xkey = request.headers.get("X-API-Key")
    if xkey:
        candidates.append(xkey)

    for token in candidates:
        # 1) JWT
        try:
            payload = jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
        except jwt.PyJWTError:
            payload = None
        if payload:
            user = _user_from_payload(payload, db)
            if user is not None:
                return user

        # 2) API key (hashed lookup)
        api_key = db.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(token))
        ).scalar_one_or_none()
        if api_key is not None:
            user = db.get(User, api_key.user_id)
            if user is not None:
                _touch_api_key(api_key, db)
                return user
    return None


def _touch_api_key(api_key: ApiKey, db: Session) -> None:
    """Track last usage, but write at most once per hour to keep hot paths cheap."""
    # SQLite stores naive UTC; keep comparisons in the same space.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if api_key.last_used_at is None or (now - api_key.last_used_at).total_seconds() > 3600:
        api_key.last_used_at = now
        db.commit()


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _authenticate(request, token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising.

    Used by public routes (e.g. GET /i/{code}) that check ownership when a
    valid credential happens to be present.
    """
    return _authenticate(request, token, db)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin privileges required")
    return current_user


def ensure_admin() -> None:
    """Create (or refresh) the admin account from OSS_ADMIN_PASSWORD."""
    if not settings.admin_password:
        return
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        if admin is None:
            db.add(User(username="admin", password_hash=hash_password(settings.admin_password), role="admin"))
        else:
            admin.password_hash = hash_password(settings.admin_password)
            admin.role = "admin"
        db.commit()
    finally:
        db.close()

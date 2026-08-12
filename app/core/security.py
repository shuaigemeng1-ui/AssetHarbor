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
_BCRYPT_SHA256_PREFIX = "bcrypt-sha256:"
# A valid, fixed bcrypt hash used only to equalize the missing-account login
# path.  The password is intentionally unknown and the result is discarded.
_DUMMY_PASSWORD_HASH = (
    _BCRYPT_SHA256_PREFIX
    + "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYw5E9IZEmZIRplu9pUeIgLd11gOBM9K"
)


def _password_digest(password: str) -> bytes:
    """Pre-hash UTF-8 bytes so bcrypt never silently truncates at 72 bytes."""
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    encoded = bcrypt.hashpw(_password_digest(password), bcrypt.gensalt()).decode("ascii")
    return _BCRYPT_SHA256_PREFIX + encoded


def verify_password(password: str, password_hash: str) -> bool:
    try:
        if password_hash.startswith(_BCRYPT_SHA256_PREFIX):
            encoded_hash = password_hash.removeprefix(_BCRYPT_SHA256_PREFIX).encode("ascii")
            return bcrypt.checkpw(_password_digest(password), encoded_hash)
        # Compatibility for accounts created before the bcrypt-SHA256 scheme.
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (UnicodeError, ValueError):
        return False


def verify_login_password(password: str, password_hash: str | None) -> bool:
    """Verify login credentials without exposing whether an account exists."""
    verified = verify_password(password, password_hash or _DUMMY_PASSWORD_HASH)
    return password_hash is not None and verified


def password_hash_needs_upgrade(password_hash: str) -> bool:
    """Return whether a successful legacy bcrypt login should be re-hashed."""
    return not password_hash.startswith(_BCRYPT_SHA256_PREFIX)


def revoke_user_jwts(user: User) -> None:
    """Invalidate JWTs with an atomic SQL-side version increment.

    Assigning a SQL expression makes SQLAlchemy emit
    ``auth_version = auth_version + 1`` instead of writing a value calculated
    from a potentially stale ORM snapshot.  Concurrent credential/role
    changes therefore cannot lose one another's revocation increments.
    """
    user.auth_version = User.auth_version + 1


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "auth_version": user.auth_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_expire_minutes),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def _user_from_payload(payload: dict, db: Session) -> User | None:
    user_id = payload.get("sub")
    # Tokens issued before auth-version support did not carry this claim.  The
    # migration initializes every existing account to version 1, so treating a
    # missing claim as 1 preserves active sessions once while still allowing a
    # later password/role change to revoke them normally.
    auth_version = payload.get("auth_version", 1)
    if user_id is None or isinstance(auth_version, bool) or not isinstance(auth_version, int):
        return None
    try:
        user = db.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if user is None or user.auth_version != auth_version:
        return None
    return user


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
    """Create or update the configured admin only when credentials changed."""
    if not settings.admin_password:
        return
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        changed = False
        if admin is None:
            db.add(User(username="admin", password_hash=hash_password(settings.admin_password), role="admin"))
            changed = True
        else:
            if not verify_password(settings.admin_password, admin.password_hash):
                admin.password_hash = hash_password(settings.admin_password)
                changed = True
            if admin.role != "admin":
                admin.role = "admin"
                changed = True
            if changed:
                revoke_user_jwts(admin)
        if changed:
            db.commit()
    finally:
        db.close()


def validate_bootstrap_state(session_factory=None) -> None:
    """Fail fast when an empty installation has no usable account path."""
    registration_unavailable = settings.allow_registration == "closed" or (
        settings.allow_registration == "invite" and not settings.invite_code
    )
    if not registration_unavailable or settings.admin_password:
        return

    factory = session_factory or SessionLocal
    db = factory()
    try:
        has_user = db.execute(select(User.id).limit(1)).scalar_one_or_none() is not None
    finally:
        db.close()
    if not has_user:
        raise RuntimeError(
            "startup refused: the users table is empty while "
            "registration is unavailable and OSS_ADMIN_PASSWORD is empty; "
            "configure OSS_ADMIN_PASSWORD, enable open registration, or configure "
            "both OSS_ALLOW_REGISTRATION=invite and OSS_INVITE_CODE for initial setup"
        )

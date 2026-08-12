"""Password hashing, JWT issuing/validation and auth dependencies."""

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

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


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _user_from_payload(payload: dict, db: Session) -> User | None:
    user_id = payload.get("sub")
    if user_id is None:
        return None
    try:
        return db.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _user_from_payload(_decode_token(token), db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising.

    Used by public routes (e.g. GET /i/{code}) that want to check
    ownership when a valid token happens to be present.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return _user_from_payload(payload, db)


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

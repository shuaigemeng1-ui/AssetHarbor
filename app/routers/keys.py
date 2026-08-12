"""Per-user API keys: create (shown once), list (prefix only), rotate, revoke."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApiKey, User
from ..schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from ..security import generate_api_key, get_current_user, hash_api_key

router = APIRouter(prefix="/api", tags=["keys"])


def _out(ak: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=ak.id,
        name=ak.name,
        key_prefix=ak.key_prefix,
        created_at=ak.created_at,
        last_used_at=ak.last_used_at,
    )


def _created(ak: ApiKey, key: str) -> ApiKeyCreated:
    return ApiKeyCreated(
        id=ak.id,
        name=ak.name,
        key=key,
        key_prefix=ak.key_prefix,
        created_at=ak.created_at,
    )


def _get_own_key(db: Session, key_id: int, user: User) -> ApiKey:
    ak = db.get(ApiKey, key_id)
    if ak is None or ak.user_id != user.id:
        raise HTTPException(status_code=404, detail="key not found")
    return ak


@router.get("/keys", response_model=list[ApiKeyOut], summary="List my API keys (prefix only)")
def list_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    rows = db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.id)
    ).scalars().all()
    return [_out(k) for k in rows]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201, summary="Create an API key (shown once)")
def create_key(
    payload: ApiKeyCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    name = payload.name.strip() if payload else ""
    key = generate_api_key()
    ak = ApiKey(
        user_id=current_user.id,
        name=name,
        key_hash=hash_api_key(key),
        key_prefix=key[:8],
    )
    db.add(ak)
    db.commit()
    db.refresh(ak)
    return _created(ak, key)


@router.post("/keys/{key_id}/rotate", response_model=ApiKeyCreated, summary="Rotate an API key (old one is revoked)")
def rotate_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    ak = _get_own_key(db, key_id, current_user)
    name = ak.name
    db.delete(ak)
    db.commit()  # the old key is now revoked

    key = generate_api_key()
    new_ak = ApiKey(
        user_id=current_user.id,
        name=name,
        key_hash=hash_api_key(key),
        key_prefix=key[:8],
    )
    db.add(new_ak)
    db.commit()
    db.refresh(new_ak)
    return _created(new_ak, key)


@router.delete("/keys/{key_id}", status_code=204, summary="Revoke an API key")
def revoke_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ak = _get_own_key(db, key_id, current_user)
    db.delete(ak)
    db.commit()

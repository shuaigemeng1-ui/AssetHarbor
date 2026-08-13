"""Per-user API keys: create (shown once), list (prefix only), rotate, revoke."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import ApiKey, RuntimeCounter, TrafficDaily, User
from ...models.base import utcnow
from ...schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from ...core.config import settings
from ...core.security import generate_api_key, hash_api_key
from ...services.library import fresh_library_user, serialized_library_lifecycle
from ...services.ratelimit import check_rate_limit
from ..deps import get_db, require_jwt_user

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


def _next_api_key_id(db: Session) -> int:
    """Allocate an ID that cannot alias any retained traffic history.

    SQLite may reuse an INTEGER PRIMARY KEY after its row is deleted. Traffic
    aggregates intentionally outlive revoked/rotated keys, so allocation must
    advance beyond both live keys and every historical key dimension. All key
    mutations and the traffic writer share the library lifecycle lease.
    """
    live_max = db.scalar(select(func.max(ApiKey.id))) or 0
    historical_max = db.scalar(select(func.max(TrafficDaily.api_key_id))) or 0
    counter = db.get(RuntimeCounter, "api_key_id")
    high_watermark = max(
        int(live_max),
        int(historical_max),
        int(counter.value) if counter is not None else 0,
    )
    next_id = high_watermark + 1
    if next_id > 9_007_199_254_740_991:
        # Keep identifiers exactly representable by JSON/JavaScript clients.
        raise HTTPException(status_code=503, detail="API key identifier space exhausted")
    if counter is None:
        db.add(RuntimeCounter(name="api_key_id", value=next_id, updated_at=utcnow()))
    else:
        counter.value = next_id
        counter.updated_at = utcnow()
    return next_id


@router.get("/keys", response_model=list[ApiKeyOut], summary="List my API keys (prefix only)")
def list_keys(
    current_user: User = Depends(require_jwt_user),
    db: Session = Depends(get_db),
) -> list[ApiKeyOut]:
    rows = db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.id)
    ).scalars().all()
    return [_out(k) for k in rows]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201, summary="Create an API key (shown once)")
@serialized_library_lifecycle
def create_key(
    payload: ApiKeyCreate | None = None,
    current_user: User = Depends(require_jwt_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    check_rate_limit(
        f"api-key-mutation:{current_user.id}:{current_user.created_at.isoformat()}",
        settings.api_key_mutation_rate_limit_per_day,
        86400,
    )
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    key_count = db.scalar(
        select(func.count()).select_from(ApiKey).where(ApiKey.user_id == current_user.id)
    ) or 0
    if key_count >= settings.max_api_keys_per_user:
        raise HTTPException(
            status_code=409,
            detail=f"at most {settings.max_api_keys_per_user} API keys are allowed per user",
        )
    name = payload.name.strip() if payload else ""
    key = generate_api_key()
    ak = ApiKey(
        id=_next_api_key_id(db),
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
@serialized_library_lifecycle
def rotate_key(
    key_id: int,
    current_user: User = Depends(require_jwt_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    check_rate_limit(
        f"api-key-mutation:{current_user.id}:{current_user.created_at.isoformat()}",
        settings.api_key_mutation_rate_limit_per_day,
        86400,
    )
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    ak = _get_own_key(db, key_id, current_user)
    name = ak.name
    new_key_id = _next_api_key_id(db)
    db.delete(ak)
    db.flush()  # revoke and replace atomically in the final commit below

    key = generate_api_key()
    new_ak = ApiKey(
        id=new_key_id,
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
@serialized_library_lifecycle
def revoke_key(
    key_id: int,
    current_user: User = Depends(require_jwt_user),
    db: Session = Depends(get_db),
) -> None:
    check_rate_limit(
        f"api-key-mutation:{current_user.id}:{current_user.created_at.isoformat()}",
        settings.api_key_mutation_rate_limit_per_day,
        86400,
    )
    db.rollback()
    current_user = fresh_library_user(db, current_user)
    ak = _get_own_key(db, key_id, current_user)
    db.delete(ak)
    db.commit()

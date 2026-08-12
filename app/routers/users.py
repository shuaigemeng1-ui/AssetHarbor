"""Admin-only endpoints (RBAC)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserOut
from ..security import require_admin

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users", response_model=list[UserOut], summary="List all users (admin only)")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [
        UserOut(id=u.id, username=u.username, role=u.role, created_at=u.created_at)
        for u in users
    ]

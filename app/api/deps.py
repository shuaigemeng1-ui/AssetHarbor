"""Shared FastAPI dependencies — single import surface for route modules."""

from ..core.database import get_db
from ..core.security import (
    get_current_user,
    get_optional_user,
    require_jwt_admin,
    require_jwt_user,
)

__all__ = [
    "get_current_user",
    "get_db",
    "get_optional_user",
    "require_jwt_admin",
    "require_jwt_user",
]

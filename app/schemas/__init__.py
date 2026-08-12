"""Pydantic schemas, one module per domain.

Re-exports everything so callers can use ``from app.schemas import X``.
"""

from .admin import AdminStats
from .auth import (
    ChangePasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from .image import ImageInfo, ImageListResponse, ImageUpdate, SignedLinkResponse, UploadResponse
from .key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from .meta import HealthResponse
from .team import (
    AddMember,
    RoleUpdate,
    TeamAdminOut,
    TeamCreate,
    TeamDetail,
    TeamMemberOut,
    TeamOut,
)

__all__ = [
    "AddMember",
    "AdminStats",
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyOut",
    "ChangePasswordRequest",
    "HealthResponse",
    "ImageInfo",
    "ImageListResponse",
    "ImageUpdate",
    "RegisterRequest",
    "ResetPasswordRequest",
    "RoleUpdate",
    "SignedLinkResponse",
    "TeamAdminOut",
    "TeamCreate",
    "TeamDetail",
    "TeamMemberOut",
    "TeamOut",
    "TokenResponse",
    "UploadResponse",
    "UserOut",
]

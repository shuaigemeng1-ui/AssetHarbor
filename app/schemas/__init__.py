"""Pydantic schemas, one module per domain.

Re-exports everything so callers can use ``from app.schemas import X``.
"""

from .admin import AdminStats, AdminUserCreate
from .auth import (
    ChangePasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from .image import ImageInfo, ImageListResponse, ImageUpdate, SignedLinkResponse, UploadResponse
from .key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from .library import (
    LibraryStats,
    MediaGroupCreate,
    MediaGroupItemsAdd,
    MediaGroupItemsResult,
    MediaGroupListResponse,
    MediaGroupOut,
    MediaGroupUpdate,
    UnifiedMediaInfo,
    UnifiedMediaListResponse,
)
from .meta import HealthResponse, PublicConfig
from .team import (
    AddMember,
    RoleUpdate,
    TeamAdminOut,
    TeamCreate,
    TeamDetail,
    TeamMemberOut,
    TeamOut,
)
from .video import (
    VideoInfo,
    VideoListResponse,
    VideoPartResponse,
    VideoUpdate,
    VideoUploadCreate,
    VideoUploadStatus,
)

__all__ = [
    "AddMember",
    "AdminStats",
    "AdminUserCreate",
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyOut",
    "ChangePasswordRequest",
    "HealthResponse",
    "ImageInfo",
    "ImageListResponse",
    "ImageUpdate",
    "LibraryStats",
    "MediaGroupCreate",
    "MediaGroupItemsAdd",
    "MediaGroupItemsResult",
    "MediaGroupListResponse",
    "MediaGroupOut",
    "MediaGroupUpdate",
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
    "UnifiedMediaInfo",
    "UnifiedMediaListResponse",
    "VideoInfo",
    "VideoListResponse",
    "VideoPartResponse",
    "VideoUpdate",
    "VideoUploadCreate",
    "VideoUploadStatus",
]

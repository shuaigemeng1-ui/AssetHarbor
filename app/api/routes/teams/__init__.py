"""Team routes: team CRUD + membership + team-space images.

The team router is large enough to warrant its own package, split by
resource: ``team`` (create/list/detail/delete), ``members`` (invite /
remove / roles) and ``space`` (team image gallery).
"""

from fastapi import APIRouter

from .members import router as members_router
from .space import router as space_router
from .team import router as team_router

router = APIRouter()
router.include_router(team_router)
router.include_router(members_router)
router.include_router(space_router)

__all__ = ["router"]

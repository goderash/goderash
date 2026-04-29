"""HTTP API layer."""

from fastapi import APIRouter

from .packs import router as packs_router
from .routes import router as core_router
from .whatif import router as whatif_router

router = APIRouter()
router.include_router(core_router)
router.include_router(packs_router)
router.include_router(whatif_router)

__all__ = ["router"]

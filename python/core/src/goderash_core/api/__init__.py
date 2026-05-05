"""HTTP API layer."""

from fastapi import APIRouter

from .auth_public import router as auth_router
from .billing import router as billing_router
from .invites import router as invites_router
from .orgs import router as orgs_router
from .packs import router as packs_router
from .routes import router as core_router
from .webhooks import router as webhooks_router
from .whatif import router as whatif_router

router = APIRouter()
router.include_router(core_router)
router.include_router(packs_router)
router.include_router(whatif_router)
router.include_router(auth_router)
router.include_router(orgs_router)
router.include_router(invites_router)
router.include_router(billing_router)
router.include_router(webhooks_router)

__all__ = ["router"]

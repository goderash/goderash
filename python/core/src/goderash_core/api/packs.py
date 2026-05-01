"""Routes for generating compliance evidence packs.

Single endpoint dispatches to whichever regulation generator is registered.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import session_scope
from ..packs import PACK_REGISTRY
from .auth import AuthContext, require_api_key

router = APIRouter(prefix="/v1/packs", tags=["packs"])


class PackRequest(BaseModel):
    start: datetime | None = Field(
        default=None,
        description="ISO timestamp; defaults to 30 days ago UTC.",
    )
    end: datetime | None = Field(
        default=None,
        description="ISO timestamp; defaults to now UTC.",
    )


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


@router.get("", tags=["packs"])
async def list_packs() -> dict[str, object]:
    return {
        "packs": sorted(PACK_REGISTRY.keys()),
        "count": len(PACK_REGISTRY),
    }


@router.post("/{regulation}", status_code=status.HTTP_200_OK)
async def generate_pack(
    regulation: str = Path(..., pattern=r"^[a-z0-9_]+$"),
    body: PackRequest = Body(default_factory=PackRequest),
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(_session),
) -> Response:
    cls = PACK_REGISTRY.get(regulation)
    if cls is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"unknown regulation {regulation!r}; available: {sorted(PACK_REGISTRY)}",
        )

    end = body.end or datetime.now(tz=timezone.utc)
    start = body.start or (end - timedelta(days=30))

    gen = cls(session=session, tenant_id=auth.tenant_id, start=start, end=end)
    await gen.collect()

    if not gen.chain_ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "ledger_chain_broken",
                "first_broken_index": gen.chain_broken_at,
                "checked": len(gen.events),
            },
        )

    artifact = gen.build()
    filename = f"goderash-{regulation}-{auth.tenant_id}-{end.date().isoformat()}.zip"
    return Response(
        content=artifact.zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Goderash-Pack-Sha256": artifact.sha256,
            "X-Goderash-Pack-Event-Count": str(artifact.manifest["event_count"]),
            "X-Goderash-Regulation": regulation,
        },
    )

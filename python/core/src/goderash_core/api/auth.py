"""API-key auth with hashed storage.

Raw keys are only seen at issue time. We persist `sha256(key)` and compare on
request. Admin endpoints accept `ADMIN_API_KEY` (also hashed at comparison).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import session_scope
from ..models.tenant import ApiKey


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    api_key_id: str | None  # None for admin
    is_admin: bool


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


async def require_api_key(
    x_goderash_api_key: str | None = Header(default=None, alias="X-Goderash-Api-Key"),
    x_goderash_tenant: str | None = Header(default=None, alias="X-Goderash-Tenant"),
    session: AsyncSession = Depends(_session),
) -> AuthContext:
    """Validate API key and bind the request to a tenant."""
    s = get_settings()

    if not x_goderash_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing X-Goderash-Api-Key")

    # Admin short-circuit — constant-time comparison
    if hmac.compare_digest(x_goderash_api_key, s.admin_api_key):
        tenant = x_goderash_tenant or s.default_tenant
        return AuthContext(tenant_id=tenant, api_key_id=None, is_admin=True)

    if not x_goderash_api_key.startswith(s.api_key_prefix):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key format")

    key_hash = _hash_key(x_goderash_api_key)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None or row.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked api key")

    # Tenant header, if present, must match the key's tenant.
    if x_goderash_tenant and x_goderash_tenant != row.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant header does not match api key")

    # Best-effort last-used update; never fail the request on this.
    try:
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == row.id)
            .values(last_used_at=datetime.now(tz=timezone.utc))
        )
    except Exception:
        pass

    return AuthContext(tenant_id=row.tenant_id, api_key_id=str(row.id), is_admin=False)


async def require_admin(auth: AuthContext = Depends(require_api_key)) -> AuthContext:
    if not auth.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin api key required")
    return auth

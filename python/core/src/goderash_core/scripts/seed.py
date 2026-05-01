"""Seed a local DB with a demo tenant + API key.

Run: `python -m goderash_core.scripts.seed`

Idempotent: if the demo tenant already exists, we issue a second key; if
you want a fresh demo, drop the `demo` rows first.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets

from sqlalchemy import select

from ..config import get_settings
from ..db import dispose_engine, session_scope
from ..models.tenant import ApiKey, Tenant


async def _seed() -> None:
    s = get_settings()

    async with session_scope() as session:
        existing = await session.execute(select(Tenant).where(Tenant.id == "demo"))
        tenant = existing.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(id="demo", display_name="Demo Co")
            session.add(tenant)
            await session.flush()
            print("created tenant: demo")

        raw = f"{s.api_key_prefix}{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        session.add(ApiKey(tenant_id="demo", label="seed", key_hash=key_hash))
        await session.flush()

        print()
        print("=" * 60)
        print("  Demo API key (shown once — save it):")
        print(f"  {raw}")
        print("=" * 60)
        print()
        print("  export GODERASH_API_KEY=" + raw)
        print("  export GODERASH_TENANT=demo")
        print("  export GODERASH_ENDPOINT=" + f"http://localhost:{s.goderash_api_port}")


def main() -> None:
    try:
        asyncio.run(_seed())
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()

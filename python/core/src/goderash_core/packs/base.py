"""Base class for regulation-specific evidence-pack generators."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ledger.chain import verify_chain
from ..models.event import EventRow


@dataclass
class Artifact:
    """A generated pack artifact ready to sign or hand to an auditor."""

    regulation: str
    tenant_id: str
    start: datetime
    end: datetime
    manifest: dict
    zip_bytes: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.zip_bytes).hexdigest()


@dataclass
class PackGenerator:
    """Subclass this. Override `regulation`, `required_event_types`, `render_controls`."""

    regulation: ClassVar[str] = "base"
    required_event_types: ClassVar[list[str]] = []
    version: ClassVar[str] = "0.1.0"

    session: AsyncSession
    tenant_id: str
    start: datetime
    end: datetime

    events: list[EventRow] = field(default_factory=list)
    chain_ok: bool = False
    chain_broken_at: int | None = None

    async def collect(self) -> None:
        """Pull the relevant events from the ledger and verify chain continuity."""
        stmt = (
            select(EventRow)
            .where(EventRow.tenant_id == self.tenant_id)
            .where(EventRow.occurred_at >= self.start)
            .where(EventRow.occurred_at <= self.end)
            .order_by(EventRow.sequence_no.asc())
        )
        result = await self.session.execute(stmt)
        self.events = list(result.scalars().all())

        ok, broken = verify_chain(
            [
                {"prev_hash": e.prev_hash, "hash": e.hash, "payload": e.payload}
                for e in self.events
            ]
        )
        self.chain_ok = ok
        self.chain_broken_at = broken

    def render_controls(self) -> dict[str, object]:
        """Override in subclasses to produce regulation-specific control evidence."""
        return {}

    def build(self) -> Artifact:
        if not self.chain_ok:
            raise RuntimeError(
                f"cannot build pack: ledger chain broken at index {self.chain_broken_at}"
            )

        manifest = {
            "regulation": self.regulation,
            "version": self.version,
            "tenant_id": self.tenant_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "event_count": len(self.events),
            "chain_verified": True,
        }
        controls = self.render_controls()
        events_json = [
            {
                "event_id": str(e.event_id),
                "sequence_no": e.sequence_no,
                "event_type": e.event_type,
                "conversation_id": e.conversation_id,
                "occurred_at": e.occurred_at.isoformat(),
                "payload": e.payload,
                "hash": e.hash,
                "prev_hash": e.prev_hash,
            }
            for e in self.events
        ]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.writestr("events.json", json.dumps(events_json, indent=2))
            z.writestr("controls.json", json.dumps(controls, indent=2))

        return Artifact(
            regulation=self.regulation,
            tenant_id=self.tenant_id,
            start=self.start,
            end=self.end,
            manifest=manifest,
            zip_bytes=buf.getvalue(),
        )

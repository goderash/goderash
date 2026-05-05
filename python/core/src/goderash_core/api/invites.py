"""Team invite and member management for dashboard users.

Authenticated by JWT session. Acting user must be owner or admin to invite/remove.

Endpoints:
- POST   /v1/orgs/{tenant_id}/invites              — send invite email
- GET    /v1/orgs/{tenant_id}/invites              — list pending invites
- DELETE /v1/orgs/{tenant_id}/invites/{invite_id}  — revoke invite
- GET    /v1/orgs/{tenant_id}/members              — list current members
- DELETE /v1/orgs/{tenant_id}/members/{user_id}   — remove member (cannot remove self)
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import session_scope
from ..email import send_email
from ..models.auth_tokens import Invite
from ..models.user import Membership, User
from ..security import SessionClaims
from .auth_public import require_session
from .orgs import _require_membership, _require_role

router = APIRouter(prefix="/v1/orgs", tags=["team"])


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


# ---- Schemas ----------------------------------------------------------------


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="developer", pattern=r"^(admin|developer|viewer)$")


class InviteOut(BaseModel):
    id: uuid.UUID
    tenant_id: str
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    joined_at: datetime
    email_verified: bool


# ---- Routes ----------------------------------------------------------------


@router.post(
    "/{tenant_id}/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=InviteOut,
)
async def create_invite(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    body: InviteRequest,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> InviteOut:
    _, user = auth
    membership = await _require_membership(session, user, tenant_id)
    _require_role(membership, ("owner", "admin"))

    settings = get_settings()
    email = body.email.lower().strip()

    # Prevent duplicate pending invites for the same email + tenant
    existing = await session.execute(
        select(Invite).where(
            Invite.tenant_id == tenant_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > datetime.now(tz=timezone.utc),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "a pending invite already exists for that email")

    # Prevent inviting someone already on the team
    already = await session.execute(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == tenant_id, User.email == email)
    )
    if already.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "that user is already a member")

    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=7)

    invite = Invite(
        tenant_id=tenant_id,
        inviter_user_id=user.id,
        email=email,
        role=body.role,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(invite)
    await session.flush()

    accept_url = f"{settings.app_base_url}/accept-invite?token={raw}"
    await send_email(
        to=email,
        subject=f"You've been invited to join a Goderash workspace",
        body=(
            f"Hi,\n\n"
            f"{user.full_name} has invited you to join their Goderash workspace "
            f"as a {body.role}.\n\n"
            f"Accept your invitation:\n{accept_url}\n\n"
            "This invite expires in 7 days.\n\nThe Goderash team"
        ),
    )

    return InviteOut(
        id=invite.id,
        tenant_id=tenant_id,
        email=email,
        role=body.role,
        expires_at=expires_at,
        created_at=invite.created_at,
    )


@router.get("/{tenant_id}/invites", response_model=list[InviteOut])
async def list_invites(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> list[InviteOut]:
    _, user = auth
    membership = await _require_membership(session, user, tenant_id)
    _require_role(membership, ("owner", "admin"))

    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        select(Invite).where(
            Invite.tenant_id == tenant_id,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > now,
        ).order_by(Invite.created_at.desc())
    )
    return [
        InviteOut(
            id=inv.id,
            tenant_id=inv.tenant_id,
            email=inv.email,
            role=inv.role,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        for inv in result.scalars().all()
    ]


@router.delete("/{tenant_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    invite_id: uuid.UUID,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> None:
    _, user = auth
    membership = await _require_membership(session, user, tenant_id)
    _require_role(membership, ("owner", "admin"))

    result = await session.execute(
        select(Invite).where(Invite.id == invite_id, Invite.tenant_id == tenant_id)
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")

    if invite.revoked_at is None:
        await session.execute(
            update(Invite)
            .where(Invite.id == invite_id)
            .values(revoked_at=datetime.now(tz=timezone.utc))
        )


@router.get("/{tenant_id}/members", response_model=list[MemberOut])
async def list_members(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> list[MemberOut]:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    result = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == tenant_id)
        .order_by(Membership.created_at.asc())
    )
    return [
        MemberOut(
            user_id=m.user_id,
            email=u.email,
            full_name=u.full_name,
            role=m.role,
            joined_at=m.created_at,
            email_verified=u.email_verified_at is not None,
        )
        for m, u in result.all()
    ]


@router.delete("/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    user_id: uuid.UUID,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> None:
    claims, acting_user = auth
    membership = await _require_membership(session, acting_user, tenant_id)
    _require_role(membership, ("owner", "admin"))

    if user_id == acting_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot remove yourself from the workspace")

    target = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.tenant_id == tenant_id
        )
    )
    target_membership = target.scalar_one_or_none()
    if target_membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")

    # Owners cannot be removed by admins
    if target_membership.role == "owner" and membership.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only owners can remove other owners")

    await session.execute(
        delete(Membership).where(
            Membership.user_id == user_id, Membership.tenant_id == tenant_id
        )
    )

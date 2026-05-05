"""Self-serve identity routes for the dashboard.

Endpoints:
- POST /v1/auth/signup            — email + password + full_name → user + tenant + first API key
- POST /v1/auth/login             — email + password → access + refresh tokens
- POST /v1/auth/refresh           — refresh token → new access token
- POST /v1/auth/logout            — revoke both JTIs; client discards tokens
- GET  /v1/auth/me                — return the current user + tenant memberships
- POST /v1/auth/forgot-password   — generate reset token, send email
- POST /v1/auth/reset-password    — consume reset token, set new password
- GET  /v1/auth/verify-email      — consume verification token
- POST /v1/auth/change-password   — change password (requires current password)
- POST /v1/auth/accept-invite     — accept a team invite (create account if needed)

API-key auth (X-Goderash-Api-Key) for SDKs is unchanged. JWTs here are used
only by the dashboard.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing.service import create_stripe_customer
from ..config import get_settings
from ..email import send_email
from ..models.auth_tokens import EmailVerificationToken, Invite, PasswordResetToken
from ..models.tenant import ApiKey, Tenant
from ..models.user import Membership, User
from ..ratelimit import limiter
from ..db import session_scope
from ..security import (
    SessionClaims,
    decode_session_token,
    hash_password,
    is_jti_revoked,
    issue_session_token,
    revoke_jti,
    verify_password,
)
from .auth import _hash_key

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_TENANT_ID_RE = re.compile(r"[^a-z0-9]+")


# ---- Shared Redis dependency ------------------------------------------------


async def _redis():
    try:
        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        await r.ping()
        return r
    except Exception:
        return None


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


# ---- Schemas ----------------------------------------------------------------


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=200)
    full_name: str = Field(..., min_length=1, max_length=255)
    org_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=12, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=12, max_length=200)


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., min_length=10)
    # Required only when creating a new account via invite
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=12, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    token_type: str = "bearer"


class SignupResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    tenant_id: str
    api_key: str
    tokens: TokenPair


class TenantMembership(BaseModel):
    tenant_id: str
    role: str
    display_name: str


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    email_verified: bool
    created_at: datetime
    memberships: list[TenantMembership]


# ---- Session dependency ----------------------------------------------------


async def require_session(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    session: AsyncSession = Depends(_session),
    redis=Depends(_redis),
) -> tuple[SessionClaims, User]:
    """Extract + validate a Bearer access token, checking JTI revocation."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "empty bearer token")

    try:
        claims = decode_session_token(token, expected_kind="access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access token expired") from None
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc

    if await is_jti_revoked(redis, claims.jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token has been revoked")

    result = await session.execute(select(User).where(User.id == claims.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return claims, user


# ---- Helpers ---------------------------------------------------------------


def _slugify_tenant(seed: str) -> str:
    base = _TENANT_ID_RE.sub("-", seed.lower()).strip("-")[:64] or "tenant"
    return f"{base}-{secrets.token_hex(3)}"


def _issue_pair(user: User) -> TokenPair:
    access_jti = secrets.token_urlsafe(16)
    refresh_jti = secrets.token_urlsafe(16)
    access, access_exp = issue_session_token(
        user_id=user.id, email=user.email, kind="access", jti=access_jti
    )
    refresh, refresh_exp = issue_session_token(
        user_id=user.id, email=user.email, kind="refresh", jti=refresh_jti
    )
    return TokenPair(
        access_token=access,
        access_expires_at=access_exp,
        refresh_token=refresh,
        refresh_expires_at=refresh_exp,
    )


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _send_verification_email(user: User, session: AsyncSession, settings) -> None:
    raw = secrets.token_urlsafe(32)
    record = EmailVerificationToken(
        user_id=user.id,
        token_hash=_hash_token(raw),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
    )
    session.add(record)
    await send_email(
        to=user.email,
        subject="Verify your Goderash email",
        body=(
            f"Hi {user.full_name},\n\n"
            f"Click the link below to verify your email address:\n"
            f"{settings.app_base_url}/verify-email?token={raw}\n\n"
            "This link expires in 24 hours.\n\nThe Goderash team"
        ),
    )


# ---- Routes ----------------------------------------------------------------


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=SignupResponse)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    body: SignupRequest,
    session: AsyncSession = Depends(_session),
) -> SignupResponse:
    settings = get_settings()
    email = body.email.lower().strip()

    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
    )
    session.add(user)
    await session.flush()

    tenant_seed = body.org_name or email.split("@", 1)[0]
    tenant_id = _slugify_tenant(tenant_seed)
    tenant = Tenant(
        id=tenant_id,
        display_name=body.org_name or f"{body.full_name}'s workspace",
    )
    session.add(tenant)

    membership = Membership(user_id=user.id, tenant_id=tenant_id, role="owner")
    session.add(membership)

    raw_key = f"{settings.api_key_prefix}{secrets.token_urlsafe(32)}"
    api_key = ApiKey(tenant_id=tenant_id, label="default", key_hash=_hash_key(raw_key))
    session.add(api_key)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "registration race detected; please retry"
        ) from exc

    # Stripe customer — fire-and-forget
    if settings.billing_enabled and settings.stripe_secret_key:
        stripe_customer_id = await create_stripe_customer(
            email=email,
            display_name=tenant.display_name,
            tenant_id=tenant_id,
            stripe_secret_key=settings.stripe_secret_key,
        )
        if stripe_customer_id:
            tenant.stripe_customer_id = stripe_customer_id

    # Send verification email — fire-and-forget
    await _send_verification_email(user, session, settings)

    return SignupResponse(
        user_id=user.id,
        email=user.email,
        tenant_id=tenant_id,
        api_key=raw_key,
        tokens=_issue_pair(user),
    )


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(_session),
) -> TokenPair:
    settings = get_settings()
    email = body.email.lower().strip()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    dummy_hash = (
        "$argon2id$v=19$m=65536,t=3,p=4$"
        "ZGVjb3lzYWx0ZGVjb3lzYWx0$ZGVjb3l2ZXJpZmlkZWNveXZlcmlmaWQ"
    )
    if user is None or not user.is_active:
        verify_password(body.password, dummy_hash)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    if settings.require_email_verification and user.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "email not verified; check your inbox for a verification link",
        )

    await session.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(tz=timezone.utc))
    )

    return _issue_pair(user)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    session: AsyncSession = Depends(_session),
    redis=Depends(_redis),
) -> TokenPair:
    try:
        claims = decode_session_token(body.refresh_token, expected_kind="refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid refresh: {exc}") from exc

    if await is_jti_revoked(redis, claims.jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token has been revoked")

    result = await session.execute(select(User).where(User.id == claims.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")

    return _issue_pair(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest = Body(default_factory=LogoutRequest),
    auth: tuple[SessionClaims, User] = Depends(require_session),
    redis=Depends(_redis),
) -> None:
    claims, _ = auth
    now = datetime.now(tz=timezone.utc)

    # Revoke the access token JTI
    access_ttl = max(0, int((claims.exp - now).total_seconds())) + 60
    await revoke_jti(redis, claims.jti, access_ttl)

    # Revoke the refresh token JTI if provided
    if body.refresh_token:
        try:
            refresh_claims = decode_session_token(body.refresh_token, expected_kind="refresh")
            refresh_ttl = max(0, int((refresh_claims.exp - now).total_seconds())) + 60
            await revoke_jti(redis, refresh_claims.jti, refresh_ttl)
        except jwt.PyJWTError:
            pass  # Bad refresh token — ignore silently


@router.get("/me", response_model=MeResponse)
async def me(
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> MeResponse:
    _, user = auth
    stmt = (
        select(Membership, Tenant)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id == user.id)
    )
    result = await session.execute(stmt)
    memberships = [
        TenantMembership(tenant_id=m.tenant_id, role=m.role, display_name=t.display_name)
        for m, t in result.all()
    ]
    return MeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
        memberships=memberships,
    )


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    session: AsyncSession = Depends(_session),
) -> dict:
    """Always returns 202 — never leaks whether the email is registered."""
    settings = get_settings()
    email = body.email.lower().strip()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        raw = secrets.token_urlsafe(32)
        record = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )
        session.add(record)
        await session.flush()

        reset_url = f"{settings.app_base_url}/reset-password?token={raw}"
        await send_email(
            to=email,
            subject="Reset your Goderash password",
            body=(
                f"Hi {user.full_name},\n\n"
                f"Click the link below to reset your password:\n{reset_url}\n\n"
                "This link expires in 1 hour. If you didn't request this, ignore this email.\n\n"
                "The Goderash team"
            ),
        )

    return {"detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(_session),
) -> dict:
    token_hash = _hash_token(body.token)
    now = datetime.now(tz=timezone.utc)

    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset token")

    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == record.id)
        .values(used_at=now)
    )
    await session.execute(
        update(User)
        .where(User.id == record.user_id)
        .values(password_hash=hash_password(body.new_password))
    )
    return {"detail": "password has been reset"}


@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    token: str = Query(..., min_length=10),
    session: AsyncSession = Depends(_session),
) -> dict:
    token_hash = _hash_token(token)
    now = datetime.now(tz=timezone.utc)

    result = await session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired verification token")

    await session.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.id == record.id)
        .values(used_at=now)
    )
    await session.execute(
        update(User).where(User.id == record.user_id).values(email_verified_at=now)
    )
    return {"detail": "email verified"}


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> dict:
    _, user = auth
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password is incorrect")

    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(password_hash=hash_password(body.new_password))
    )
    return {"detail": "password updated"}


@router.post("/accept-invite", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def accept_invite(
    request: Request,
    body: AcceptInviteRequest,
    session: AsyncSession = Depends(_session),
) -> TokenPair:
    """Accept a team invite. Creates the user account if they don't have one yet."""
    token_hash = _hash_token(body.token)
    now = datetime.now(tz=timezone.utc)

    result = await session.execute(
        select(Invite).where(
            Invite.token_hash == token_hash,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > now,
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired invite")

    # Find or create user
    user_result = await session.execute(select(User).where(User.email == invite.email))
    user = user_result.scalar_one_or_none()

    if user is None:
        if not body.full_name or not body.password:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "full_name and password are required to create a new account",
            )
        user = User(
            email=invite.email,
            password_hash=hash_password(body.password),
            full_name=body.full_name.strip(),
            email_verified_at=now,  # trust invite as implicit verification
        )
        session.add(user)
        await session.flush()
    else:
        # Existing user — check they're not already a member
        existing_membership = await session.execute(
            select(Membership).where(
                Membership.user_id == user.id, Membership.tenant_id == invite.tenant_id
            )
        )
        if existing_membership.scalar_one_or_none() is not None:
            await session.execute(
                update(Invite).where(Invite.id == invite.id).values(accepted_at=now)
            )
            return _issue_pair(user)

    membership = Membership(user_id=user.id, tenant_id=invite.tenant_id, role=invite.role)
    session.add(membership)

    await session.execute(
        update(Invite).where(Invite.id == invite.id).values(accepted_at=now)
    )

    return _issue_pair(user)

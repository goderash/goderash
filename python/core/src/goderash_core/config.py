"""Typed, fail-fast configuration.

Every setting is validated at import time. Missing or malformed values crash
the process on boot — never silently in the first request.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration.

    Loaded from environment variables; `.env` in the project root is read
    automatically in dev. In production, env vars are the source of truth.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    goderash_env: str = Field(default="dev", pattern=r"^(dev|staging|prod)$")
    goderash_log_level: str = Field(default="INFO")
    goderash_api_host: str = Field(default="0.0.0.0")
    goderash_api_port: int = Field(default=8000, ge=1, le=65535)

    # Security
    jwt_secret: str = Field(..., min_length=32)
    jwt_algorithm: str = Field(default="HS256")
    api_key_prefix: str = Field(default="gdr_")
    admin_api_key: str = Field(..., min_length=16)

    # Database
    database_url: str = Field(...)
    database_pool_size: int = Field(default=20, ge=1, le=200)
    database_pool_max_overflow: int = Field(default=10, ge=0, le=200)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # CORS
    cors_origins: str = Field(default="http://localhost:3000")

    # Observability
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    prometheus_enabled: bool = True
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None

    # Compliance packs
    pack_signing_key_path: Path = Field(default=Path("./secrets/pack-signing.key"))
    pack_output_dir: Path = Field(default=Path("./data/packs"))

    # Multi-tenant
    default_tenant: str = Field(default="goderash-internal")
    enforce_tenant_isolation: bool = True

    # Ingestion limits
    max_event_batch_size: int = Field(default=500, ge=1, le=10_000)
    max_event_payload_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    ingest_rate_limit_per_minute: int = Field(default=6000, ge=1)

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, v: str) -> str:
        if "+asyncpg" not in v and "+aiosqlite" not in v:
            raise ValueError(
                "DATABASE_URL must use an async driver "
                "(postgresql+asyncpg://... or sqlite+aiosqlite://...)"
            )
        return v

    @field_validator("cors_origins")
    @classmethod
    def split_origins(cls, v: str) -> str:
        return v  # kept as string; split at use-site

    @model_validator(mode="after")
    def production_requires_real_secrets(self) -> "Settings":
        if self.goderash_env == "prod":
            if self.jwt_secret.startswith("change-me") or "change_me" in self.admin_api_key:
                raise ValueError(
                    "Production environment detected with placeholder secrets. Rotate them."
                )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton accessor; validated once on first use."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings

"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import __version__
from .api import router
from .config import get_settings
from .db import dispose_engine, get_engine
from .ratelimit import limiter


def _configure_logging(level: str) -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    _configure_logging(s.goderash_log_level)
    # Eagerly construct the engine so DB misconfig fails at startup, not mid-request.
    get_engine()
    structlog.get_logger().info("goderash.core.startup", version=__version__, env=s.goderash_env)
    try:
        yield
    finally:
        await dispose_engine()
        structlog.get_logger().info("goderash.core.shutdown")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Goderash Core",
        description="Audit & governance fabric for regulated AI agents",
        version=__version__,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    if s.prometheus_enabled:
        app.mount("/metrics", make_asgi_app())

    return app


app = create_app()


def cli() -> None:
    """Console-script entry point: `goderash-core` runs uvicorn."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "goderash_core.main:app",
        host=s.goderash_api_host,
        port=s.goderash_api_port,
        log_level=s.goderash_log_level.lower(),
    )


if __name__ == "__main__":
    cli()

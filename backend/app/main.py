"""FastAPI application factory."""
from __future__ import annotations

import structlog
from fastapi import FastAPI
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.database import init_db
from app.config import get_settings
from app.lmdb_client import init_lmdb
from app.routers import auth, health, users, webhooks, pages


# Config setup
settings = get_settings()
log = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_api])


def create_app() -> FastAPI:
  app = FastAPI(
    title="Subconscious API",
    description="Identity, OAuth, and webhook sync for the Subconscious agentic UI.",
    version=settings.app_version,
    # Disable interactive docs in production
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url="/openapi.json",
  )

  # ── Rate limiting ─────────────────────────────────────────────────────────
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

  # ── Trusted host (prod only) ──────────────────────────────────────────────
  if settings.is_production:
    app.add_middleware(
      TrustedHostMiddleware,
      allowed_hosts=[
        "api.subconscious.chat",
        "subconscious.chat",
        "app.subconscious.chat",
        "docs.subconscious.chat",
      ],
    )

  # ── CORS ─────────────────────────────────────────────────────────────────
  app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Subconscious-Signature"],
    expose_headers=["X-Subconscious-Request-Id"],
  )

  # ── Routers ───────────────────────────────────────────────────────────────
  app.include_router(health.router)
  app.include_router(pages.router, tags=["pages"])
  app.include_router(auth.router, prefix="/auth", tags=["auth"])
  app.include_router(users.router, prefix="/users", tags=["users"])
  app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

  # ── Lifecycle ─────────────────────────────────────────────────────────────
  if not settings.app_env == "testing":
    @app.on_event("startup")
    async def on_startup() -> None:
      await init_db()
      await init_lmdb()
      log.info("subconscious_api_started", env=settings.app_env, version=settings.app_version)

  @app.on_event("shutdown")
  async def on_shutdown() -> None:
    log.info("subconscious_api_stopped")

  return app


app = create_app()

"""Health check router."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.lmdb_client import get_lmdb

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def liveness() -> dict:
  return {"status": "ok", "version": settings.app_version, "env": settings.app_env}


@router.get("/health/ready")
async def readiness() -> dict:
  checks: dict[str, str] = {}

  # DB
  try:
    async with engine.connect() as conn:
      await conn.execute(text("SELECT 1"))
    checks["database"] = "ok"
  except Exception as exc:
    checks["database"] = f"error: {exc}"

  # LMDB
  try:
    r = get_lmdb()
    await r.ping()
    checks["lmdb"] = "ok"
  except Exception as exc:
    checks["lmdb"] = f"error: {exc}"

  overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
  return {"status": overall, "checks": checks}

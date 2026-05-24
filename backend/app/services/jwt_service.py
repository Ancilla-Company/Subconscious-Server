"""JWT issuance, verification, and refresh token management."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.config import get_settings
from app.lmdb_client import (
  get_refresh_token_user,
  revoke_refresh_token,
  store_refresh_token,
)

settings = get_settings()


def _now() -> datetime:
  return datetime.now(UTC)


def create_access_token(user_id: str, email: str) -> tuple[str, int]:
  """Return (encoded_jwt, expires_in_seconds)."""
  expire_seconds = settings.jwt_access_token_expire_minutes * 60
  payload = {
    "sub": user_id,
    "email": email,
    "iat": _now(),
    "exp": _now() + timedelta(seconds=expire_seconds),
    "jti": str(uuid.uuid4()),
    "type": "access",
  }
  token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
  return token, expire_seconds


async def create_refresh_token(user_id: str) -> str:
  """Create an opaque refresh token stored in Redis."""
  jti = str(uuid.uuid4())
  await store_refresh_token(jti, user_id)
  return jti


async def rotate_refresh_token(old_jti: str) -> tuple[str, str] | None:
  """Validate old refresh token, revoke it, issue a new one. Returns (user_id, new_jti)."""
  user_id = await get_refresh_token_user(old_jti)
  if not user_id:
    return None
  await revoke_refresh_token(old_jti)
  new_jti = await create_refresh_token(user_id)
  return user_id, new_jti


def decode_access_token(token: str) -> dict:
  """Decode and validate a JWT access token. Raises JWTError on failure."""
  payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
  if payload.get("type") != "access":
    raise JWTError("Not an access token")
  return payload

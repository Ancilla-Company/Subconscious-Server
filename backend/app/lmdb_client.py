""" LMDB-backed key/value helpers — state/nonce store, JWT revocation.

  This keeps the same async function signatures as the previous client so
  the rest of the codebase doesn't need to change. LMDB operations are
  synchronous; we run them in a thread to avoid blocking the event loop.
"""
from __future__ import annotations

import os
import json
import time
import lmdb
import asyncio
from typing import Optional

from app.config import get_settings

settings = get_settings()

_env: Optional[lmdb.Environment] = None


async def init_lmdb() -> None:
  """Initialise the LMDB environment.
  """
  global _env
  os.makedirs(settings.lmdb_path, exist_ok=True)

  def _open() -> lmdb.Environment:
    return lmdb.open(
      settings.lmdb_path,
      map_size=settings.lmdb_map_size,
      max_dbs=1,
      # Allow many concurrent read transactions (one per async task).
      # LMDB readers never block writers and writers never block readers
      # (MVCC snapshot isolation), so a high ceiling is safe.
      max_readers=256,
      # readahead=False improves random-access latency; our keys are short
      # and access patterns are scattered, so OS readahead wastes I/O.
      readahead=False,
    )

  _env = await asyncio.to_thread(_open)


def get_lmdb():
  """Return a small shim with an async `ping()` method so health checks work."""
  if _env is None:
    raise RuntimeError("LMDB not initialised — call init_lmdb() first")

  class _Shim:
    async def ping(self) -> bool:  # pragma: no cover - trivial
      def _check():
        with _env.begin(write=False) as txn:  # explicit read-only
          return True

      return await asyncio.to_thread(_check)

  return _Shim()


# ── Helpers ───────────────────────────────────────────────────────────────────

STATE_TTL = 600  # 10 minutes — OAuth state/nonce
REFRESH_TOKEN_TTL = 60 * 60 * 24 * 30  # 30 days


def _key(name: str) -> bytes:
  return name.encode("utf-8")


def _to_bytes(val: bytes | memoryview | None) -> bytes | None:
  if val is None:
    return None
  if isinstance(val, memoryview):
    return val.tobytes()
  return val


async def store_oauth_state(state: str, data: dict[str, str]) -> None:
  if _env is None:
    raise RuntimeError("LMDB not initialised")

  key = _key(f"oauth_state:{state}")
  payload = {
    "data": data,
    "expires_at": int(time.time()) + STATE_TTL,
  }

  def _write():
    with _env.begin(write=True) as txn:
      txn.put(key, json.dumps(payload).encode("utf-8"))

  await asyncio.to_thread(_write)


async def consume_oauth_state(state: str) -> dict[str, str] | None:
  if _env is None:
    raise RuntimeError("LMDB not initialised")

  key = _key(f"oauth_state:{state}")

  def _consume() -> Optional[dict[str, str]]:
    # Phase 1: read-only — never blocks concurrent readers.
    with _env.begin(write=False) as txn:
      val = _to_bytes(txn.get(key))
    if not val:
      return None
    try:
      payload = json.loads(val.decode("utf-8"))
    except Exception:
      payload = None
    valid = payload is not None and payload.get("expires_at", 0) >= int(time.time())
    # Phase 2: write-only to delete the consumed/expired key.
    with _env.begin(write=True) as txn:
      txn.delete(key)
    return payload.get("data") if valid else None

  return await asyncio.to_thread(_consume)


async def store_refresh_token(jti: str, user_id: str) -> None:
  if _env is None:
    raise RuntimeError("LMDB not initialised")

  key = _key(f"rt:{jti}")
  payload = {"user_id": user_id, "expires_at": int(time.time()) + REFRESH_TOKEN_TTL}

  def _write():
    with _env.begin(write=True) as txn:
      txn.put(key, json.dumps(payload).encode("utf-8"))

  await asyncio.to_thread(_write)


async def get_refresh_token_user(jti: str) -> str | None:
  if _env is None:
    raise RuntimeError("LMDB not initialised")

  key = _key(f"rt:{jti}")

  def _read() -> Optional[str]:
    # Phase 1: read-only — doesn't block any other reader or writer.
    with _env.begin(write=False) as txn:
      val = _to_bytes(txn.get(key))
    if not val:
      return None
    try:
      payload = json.loads(val.decode("utf-8"))
    except Exception:
      # Corrupt entry — delete it in a separate write txn.
      with _env.begin(write=True) as txn:
        txn.delete(key)
      return None
    if payload.get("expires_at", 0) < int(time.time()):
      # Expired — lazy-delete in a write txn, don't block caller.
      with _env.begin(write=True) as txn:
        txn.delete(key)
      return None
    return payload.get("user_id")

  return await asyncio.to_thread(_read)


async def revoke_refresh_token(jti: str) -> None:
  if _env is None:
    raise RuntimeError("LMDB not initialised")

  key = _key(f"rt:{jti}")

  def _delete():
    with _env.begin(write=True) as txn:
      txn.delete(key)

  await asyncio.to_thread(_delete)


async def revoke_all_user_tokens(user_id: str) -> None:
  """Remove all refresh tokens for a user (logout everywhere)."""
  if _env is None:
    raise RuntimeError("LMDB not initialised")

  def _scan_and_delete():
    keys_to_remove: list[bytes] = []
    with _env.begin() as txn:
      with txn.cursor() as cur:
        if not cur.first():
          return
        while True:
          k = cur.key()
          if k.startswith(b"rt:"):
            try:
              b = _to_bytes(cur.value())
              if b is None:
                raise ValueError("empty value")
              payload = json.loads(b.decode("utf-8"))
            except Exception:
              # malformed — schedule for deletion
              keys_to_remove.append(k)
            else:
              if payload.get("user_id") == user_id:
                keys_to_remove.append(k)
          if not cur.next():
            break
    if not keys_to_remove:
      return
    with _env.begin(write=True) as wtxn:
      for k in keys_to_remove:
        wtxn.delete(k)

  await asyncio.to_thread(_scan_and_delete)

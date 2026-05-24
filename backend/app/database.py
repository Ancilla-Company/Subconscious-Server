""" Async SQLAlchemy engine, session factory, and Base. """
from __future__ import annotations

import os
from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


settings = get_settings()

# Ensure the directory for a file-based SQLite DB exists before engine
# creation — prevents sqlite3.OperationalError: unable to open database file.
try:
  url = make_url(settings.database_url)
except Exception:
  url = None

if url is not None and url.drivername and url.drivername.startswith("sqlite"):
  db_path = url.database
  if db_path and db_path != ":memory":
    db_dir = os.path.dirname(db_path)
    if db_dir:
      os.makedirs(db_dir, exist_ok=True)


# SQLite does not support QueuePool (pool_size / max_overflow).
# NullPool creates a fresh connection per request and releases it immediately,
# which is the correct behaviour for aiosqlite in an async context.
engine = create_async_engine(
  settings.database_url,
  echo=not settings.is_production,
  poolclass=NullPool,
)

# Enable WAL mode for SQLite so reads are never blocked by a concurrent write.
# WAL keeps readers and writers out of each other's way via MVCC snapshots.
# synchronous=NORMAL is safe with WAL and halves fsync cost vs. FULL.
if engine.dialect.name == "sqlite":
  @event.listens_for(engine.sync_engine, "connect")
  def _set_sqlite_pragma(conn, _record) -> None:
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-8000")  # 8 MiB page cache
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
  bind=engine,
  class_=AsyncSession,
  expire_on_commit=False,
  autoflush=False,
)


class Base(DeclarativeBase):
  pass


async def init_db() -> None:
  """Create all tables (use Alembic for production migrations)."""
  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:  # type: ignore[misc]
  async with AsyncSessionLocal() as session:
    yield session

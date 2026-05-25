"""Shared test fixtures."""
from __future__ import annotations

import os
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import create_app
from app.config import get_settings
from app.database import Base, get_db
from app.lmdb_client import init_lmdb
from app.services.jwt_service import create_access_token

# ── Test DB (SQLite in-memory via aiosqlite) ───────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "testing"


@pytest.fixture(scope="session")
def anyio_backend():
  return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def engine():
  eng = create_async_engine(TEST_DB_URL, echo=False)
  async with eng.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
  yield eng
  await eng.dispose()


@pytest_asyncio.fixture()
async def db(engine):
  async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
  async with async_session() as session:
    yield session


@pytest.fixture(scope="session")
def app(engine):
  """
  Creates a FastAPI app instance with DB and Redis initialization disabled 
  to prevent connection attempts to production-like services during tests.
  """
  from fastapi import FastAPI
  from app.main import create_app
  from app.database import get_db

  app = create_app()

  # We remove the startup handlers that try to connect to real DB/Redis
  # In newer FastAPI we'd use lifespan, but here it's on_event
  # We can't easily remove them from the 'app' object once added without reaching into internals
  # Instead, we will override the 'get_db' dependency.

  return app


@pytest_asyncio.fixture()
async def client(app, db: AsyncSession):
  from app.database import get_db

  async def override_get_db():
    yield db

  app.dependency_overrides[get_db] = override_get_db

  async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
    yield ac

  app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def auth_client(app, db: AsyncSession):
  """
  Returns an AsyncClient with a valid Authorization header for a test user.
  """
  from app.database import get_db
  import uuid
  from app.models.user import User

  # Override get_db to use our test session
  async def override_get_db():
    yield db

  app.dependency_overrides[get_db] = override_get_db

  user_id = uuid.uuid4()
  user = User(
    id=user_id,
    email="test_auth@example.com",
    display_name="Test Auth User",
  )
  db.add(user)
  await db.commit()
  await db.refresh(user)

  token, _ = create_access_token(user_id=str(user.id), email=user.email)

  async with AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://test",
    headers={"Authorization": f"Bearer {token}"}
  ) as ac:
    yield ac

  # Clear overrides after test
  app.dependency_overrides.clear()


@pytest.fixture
def fernet_key():
  return Fernet.generate_key().decode()

"""Integration tests for auth endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
  r = await client.get("/health")
  assert r.status_code == 200
  assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_providers_unauthenticated(client: AsyncClient):
  r = await client.get("/auth/providers")
  assert r.status_code == 200
  providers = r.json()
  # API-key providers are always listed
  slugs = [p["slug"] for p in providers]
  assert "anthropic" in slugs
  assert "deepseek" in slugs
  # All have required fields
  for p in providers:
    assert "slug" in p
    assert "auth_type" in p
    assert "is_connected" in p


@pytest.mark.asyncio
async def test_apikey_requires_auth(client: AsyncClient):
  r = await client.post("/auth/apikey", json={"provider_slug": "anthropic", "api_key": "sk-ant-123456789"})
  assert r.status_code == 401


@pytest.mark.asyncio
async def test_unknown_oauth_provider(client: AsyncClient):
  r = await client.get("/auth/nonexistent/login")
  assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_me_requires_auth(client: AsyncClient):
  r = await client.get("/auth/me")
  assert r.status_code == 401


@pytest.mark.asyncio
async def test_users_me_requires_auth(client: AsyncClient):
  r = await client.get("/users/me")
  assert r.status_code == 401


@pytest.mark.asyncio
async def test_webhooks_requires_auth(client: AsyncClient):
  r = await client.get("/webhooks")
  assert r.status_code == 401

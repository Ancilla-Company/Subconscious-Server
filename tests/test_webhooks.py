"""Webhook CRUD and delivery tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_webhook_requires_auth(client: AsyncClient):
  r = await client.post(
    "/webhooks",
    json={"url": "https://example.com/hook", "events": ["agent.run.completed"]},
  )
  assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_webhooks_requires_auth(client: AsyncClient):
  r = await client.get("/webhooks")
  assert r.status_code == 401

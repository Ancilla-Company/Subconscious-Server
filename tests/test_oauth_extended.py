"""Integration tests for OAuth authentication and linking."""
from __future__ import annotations

import json
import httpx
import respx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.token_service import decrypt_token
from app.models.user import User, OAuthAccount, ApiKeyAccount


@pytest.mark.asyncio
async def test_oauth_github_login_flow(client: AsyncClient, db, respx_mock):
  """
  Simulates the OAuth callback from GitHub.
  This usually involves:
  1. Receiving a callback with code/state.
  2. Exchanging code for token.
  3. Fetching user info from provider.
  4. Creating user and OAuth account.
  """
  # State parameter for OAuth callback
  state = "test_state_github"

  # Mock GitHub Token Endpoint
  respx_mock.post("https://github.com/login/oauth/access_token").mock(
    return_value=httpx.Response(200, json={
      "access_token": "gh_access_token_123",
      "token_type": "bearer",
      "scope": "user:email"
    })
  )

  # Mock GitHub User Endpoint
  respx_mock.get("https://api.github.com/user").mock(
    return_value=httpx.Response(200, json={
      "id": 12345,
      "login": "github_user",
      "name": "GitHub User",
      "email": "github@example.com",
      "avatar_url": "https://avatars.githubusercontent.com/u/12345"
    })
  )

  # Mock credentials check and the stored OAuth state since tests don't run startup
  with patch("app.services.provider_service.get_client_credentials") as mock_creds, \
      patch("app.routers.auth.consume_oauth_state", new_callable=AsyncMock) as mock_consume, \
      patch("app.routers.auth.create_refresh_token", new_callable=AsyncMock) as mock_create_refresh:
    mock_creds.return_value = ("fake_id", "fake_secret")
    mock_consume.return_value = {"slug": "github", "mode": "login"}
    mock_create_refresh.return_value = "fake_refresh_jti"

    # Trigger callback
    response = await client.get(f"/auth/github/callback?code=gh_code_123&state={state}&native=true")

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "github@example.com"

  # Verify DB state
  result = await db.execute(select(User).where(User.email == "github@example.com"))
  user = result.scalar_one_or_none()
  assert user is not None
  assert user.display_name == "GitHub User"

  result = await db.execute(select(OAuthAccount).where(OAuthAccount.user_id == user.id))
  account = result.scalar_one_or_none()
  assert account is not None
  assert account.provider_slug == "github"
  assert decrypt_token(account.enc_access_token) == "gh_access_token_123"


@pytest.mark.asyncio
async def test_apikey_connect_workflow(auth_client: AsyncClient, db: AsyncSession):
  """Test connecting an API-key provider like Anthropic."""
  resp = await auth_client.post("/auth/apikey", json={
    "provider_slug": "anthropic",
    "api_key": "sk-ant-test-12345"
  })
  assert resp.status_code == 201
  data = resp.json()
  assert data["provider_slug"] == "anthropic"
  assert data["key_hint"] == "...2345"

  # Get the user_id from the session mock
  # (Since auth_client is a fixture, we can just fetch the user we added)
  result = await db.execute(select(User).where(User.email == "test_auth@example.com"))
  user = result.scalar_one()

  # Check DB
  result = await db.execute(select(ApiKeyAccount).where(ApiKeyAccount.user_id == user.id))
  account = result.scalar_one_or_none()
  assert account is not None
  assert account.provider_slug == "anthropic"
  assert decrypt_token(account.enc_api_key) == "sk-ant-test-12345"


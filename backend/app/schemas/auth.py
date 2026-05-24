"""Pydantic schemas for auth endpoints."""
from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field


class ProviderInfo(BaseModel):
  slug: str
  display_name: str
  icon_url: str
  auth_type: Literal["oauth2", "apikey"]
  is_connected: bool = False


class TokenResponse(BaseModel):
  access_token: str
  token_type: str = "bearer"
  expires_in: int  # seconds


class UserSummary(BaseModel):
  id: str
  email: EmailStr
  display_name: str | None
  avatar_url: str | None
  connected_providers: list[str]


class AuthResponse(BaseModel):
  access_token: str
  token_type: str = "bearer"
  expires_in: int
  user: UserSummary


class ApiKeyRequest(BaseModel):
  provider_slug: str = Field(..., min_length=1, max_length=64)
  api_key: str = Field(..., min_length=8)


class ApiKeyResponse(BaseModel):
  provider_slug: str
  key_hint: str           # e.g. "...8f3c"
  message: str = "API key stored securely."


class RefreshRequest(BaseModel):
  refresh_token: str


class LoginInitResponse(BaseModel):
  """Returned to native clients that cannot follow redirects."""
  url: str
  state: str

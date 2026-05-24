"""Pydantic schemas for user endpoints."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, EmailStr


class ConnectedProvider(BaseModel):
  provider_slug: str
  auth_type: str           # "oauth2" | "apikey"
  display_name: str
  key_hint: str | None     # only for apikey type
  linked_at: datetime


class UserProfile(BaseModel):
  id: str
  email: EmailStr
  display_name: str | None
  avatar_url: str | None
  created_at: datetime
  connected_providers: list[ConnectedProvider]


class UserUpdate(BaseModel):
  display_name: str | None = None
  avatar_url: str | None = None

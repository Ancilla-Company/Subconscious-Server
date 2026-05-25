"""Pydantic schemas for webhook endpoints."""
from __future__ import annotations

from typing import Any
from datetime import datetime
from pydantic import AnyHttpUrl, BaseModel, Field


WEBHOOK_EVENTS = [
  "agent.run.completed",
  "agent.run.failed",
  "tool.connected",
  "tool.disconnected",
  "account.linked",
  "account.unlinked",
  "key.added",
  "key.deleted",
]


class WebhookCreate(BaseModel):
  url: AnyHttpUrl
  description: str | None = Field(None, max_length=500)
  events: list[str] = Field(..., min_length=1)
  secret: str | None = None  # auto-generated if None

  model_config = {"json_schema_extra": {"examples": [
    {
      "url": "https://my-tool.example.com/hook",
      "description": "Notify when agent run completes",
      "events": ["agent.run.completed", "agent.run.failed"],
    }
  ]}}


class WebhookUpdate(BaseModel):
  url: AnyHttpUrl | None = None
  description: str | None = None
  events: list[str] | None = None
  is_active: bool | None = None


class WebhookResponse(BaseModel):
  id: str
  url: str
  description: str | None
  events: list[str]
  is_active: bool
  secret_hint: str    # last 6 chars of secret — full secret shown only at creation
  created_at: datetime
  updated_at: datetime


class WebhookCreatedResponse(WebhookResponse):
  secret: str         # shown ONCE at creation time


class DeliveryResponse(BaseModel):
  id: str
  webhook_id: str
  event_type: str
  payload: dict[str, Any]
  response_status: int | None
  attempt_count: int
  delivered_at: datetime | None
  created_at: datetime

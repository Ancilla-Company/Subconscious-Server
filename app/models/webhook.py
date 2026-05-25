"""ORM models — Webhook and WebhookDelivery."""

from __future__ import annotations

import uuid
from datetime import datetime
from app.models.user import GUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, JSON

from app.database import Base


class Webhook(Base):
  __tablename__ = "webhook"

  id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
  user_id: Mapped[uuid.UUID] = mapped_column(
    GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
  )
  url: Mapped[str] = mapped_column(Text, nullable=False)
  enc_secret: Mapped[str] = mapped_column(
    Text, nullable=False
  )  # Fernet-encrypted HMAC secret
  events: Mapped[JSON] = mapped_column(JSON, nullable=False, default=list)
  description: Mapped[str | None] = mapped_column(Text)
  is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
  )
  updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
  )

  user: Mapped["User"] = relationship("User", back_populates="webhooks")  # noqa: F821
  deliveries: Mapped[list[WebhookDelivery]] = relationship(
    "WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan"
  )


class WebhookDelivery(Base):
  __tablename__ = "webhook_delivery"

  id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
  webhook_id: Mapped[uuid.UUID] = mapped_column(
    GUID(), ForeignKey("webhook.id", ondelete="CASCADE"), nullable=False, index=True
  )
  event_type: Mapped[str] = mapped_column(String(128), nullable=False)
  payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
  response_status: Mapped[int | None] = mapped_column(Integer)
  response_body: Mapped[str | None] = mapped_column(Text)
  attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
  next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
  delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now()
  )

  webhook: Mapped[Webhook] = relationship("Webhook", back_populates="deliveries")

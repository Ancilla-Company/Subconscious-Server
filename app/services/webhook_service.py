"""Webhook delivery service — async delivery with exponential backoff."""
from __future__ import annotations

import hmac
import json
import time
import uuid
import httpx
import hashlib
import structlog
from typing import Any
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.services.token_service import decrypt_token

log = structlog.get_logger()
settings = get_settings()


def generate_secret() -> str:
  import secrets
  return secrets.token_hex(32)


def compute_signature(secret: str, body: bytes) -> str:
  sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
  return f"sha256={sig}"


async def dispatch_event(
  db: "AsyncSession",  # noqa: F821
  *,
  user_id: uuid.UUID,
  event_type: str,
  payload: dict[str, Any],
) -> None:
  """Find all active webhooks for a user listening to event_type and enqueue delivery."""
  from sqlalchemy import select
  from app.models.webhook import Webhook, WebhookDelivery

  result = await db.execute(
    select(Webhook).where(
      Webhook.user_id == user_id,
      Webhook.is_active == True,  # noqa: E712
      Webhook.events.contains([event_type]),  # type: ignore[arg-type]
    )
  )
  webhooks = result.scalars().all()

  for webhook in webhooks:
    delivery = WebhookDelivery(
      id=uuid.uuid4(),
      webhook_id=webhook.id,
      event_type=event_type,
      payload_json=payload,
      attempt_count=0,
    )
    db.add(delivery)
    await db.flush()

    # Fire-and-forget delivery attempt (BackgroundTasks would be wired in the router)
    try:
      await _attempt_delivery(db, delivery=delivery, webhook=webhook)
    except Exception as exc:
      log.warning("webhook_delivery_failed", delivery_id=str(delivery.id), error=str(exc))


async def _attempt_delivery(
  db: "AsyncSession",  # noqa: F821
  *,
  delivery: "WebhookDelivery",  # noqa: F821
  webhook: "Webhook",  # noqa: F821
) -> None:
  secret = decrypt_token(webhook.enc_secret)
  body = json.dumps(delivery.payload_json, separators=(",", ":")).encode()
  timestamp = str(int(time.time()))
  signature = compute_signature(secret, body)

  headers = {
    "Content-Type": "application/json",
    "X-Subconscious-Event": delivery.event_type,
    "X-Subconscious-Delivery": str(delivery.id),
    "X-Subconscious-Timestamp": timestamp,
    "X-Subconscious-Signature": signature,
  }

  max_retries = settings.webhook_max_retries
  backoff_base = settings.webhook_retry_backoff_base
  timeout = settings.webhook_delivery_timeout

  for attempt in range(max_retries):
    delivery.attempt_count = attempt + 1
    try:
      async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(str(webhook.url), content=body, headers=headers)
      delivery.response_status = resp.status_code
      delivery.response_body = resp.text[:2000]

      if resp.is_success:
        delivery.delivered_at = datetime.now(UTC)
        delivery.next_retry_at = None
        await db.flush()
        log.info("webhook_delivered", delivery_id=str(delivery.id), status=resp.status_code)
        return

    except httpx.RequestError as exc:
      delivery.response_status = None
      delivery.response_body = str(exc)[:500]

    # Exponential backoff
    wait = backoff_base ** attempt
    delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=wait)
    await db.flush()
    log.warning(
      "webhook_delivery_retry",
      delivery_id=str(delivery.id),
      attempt=attempt + 1,
      wait_s=wait,
    )

  log.error("webhook_delivery_exhausted", delivery_id=str(delivery.id))

"""Webhooks router — CRUD, test delivery, delivery history, secret rotation."""
from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery
from app.schemas.webhook import (
  DeliveryResponse,
  WebhookCreate,
  WebhookCreatedResponse,
  WebhookResponse,
  WebhookUpdate,
)
from app.services.token_service import decrypt_token, encrypt_token, mask_key
from app.services.webhook_service import dispatch_event, generate_secret

router = APIRouter()


def _to_response(wh: Webhook, reveal_secret: str | None = None) -> WebhookResponse | WebhookCreatedResponse:
  plain_secret = decrypt_token(wh.enc_secret)
  base = dict(
    id=str(wh.id),
    url=str(wh.url),
    description=wh.description,
    events=wh.events,
    is_active=wh.is_active,
    secret_hint="..." + plain_secret[-6:],
    created_at=wh.created_at,
    updated_at=wh.updated_at,
  )
  if reveal_secret:
    return WebhookCreatedResponse(**base, secret=reveal_secret)
  return WebhookResponse(**base)


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
  limit: int = Query(50, le=200),
  offset: int = Query(0, ge=0),
) -> list[WebhookResponse]:
  result = await db.execute(
    select(Webhook)
    .where(Webhook.user_id == current_user.id)
    .order_by(Webhook.created_at.desc())
    .limit(limit)
    .offset(offset)
  )
  return [_to_response(wh) for wh in result.scalars()]


@router.post("", response_model=WebhookCreatedResponse, status_code=201)
async def create_webhook(
  body: WebhookCreate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> WebhookCreatedResponse:
  plain_secret = body.secret or generate_secret()
  wh = Webhook(
    id=uuid.uuid4(),
    user_id=current_user.id,
    url=str(body.url),
    enc_secret=encrypt_token(plain_secret),
    events=body.events,
    description=body.description,
    is_active=True,
  )
  db.add(wh)
  await db.commit()
  await db.refresh(wh)
  return _to_response(wh, reveal_secret=plain_secret)  # type: ignore[return-value]


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
  webhook_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> WebhookResponse:
  wh = await _get_owned(db, webhook_id, current_user)
  return _to_response(wh)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
  webhook_id: uuid.UUID,
  body: WebhookUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> WebhookResponse:
  wh = await _get_owned(db, webhook_id, current_user)
  if body.url is not None:
    wh.url = str(body.url)
  if body.description is not None:
    wh.description = body.description
  if body.events is not None:
    wh.events = body.events
  if body.is_active is not None:
    wh.is_active = body.is_active
  await db.commit()
  await db.refresh(wh)
  return _to_response(wh)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
  webhook_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> None:
  wh = await _get_owned(db, webhook_id, current_user)
  await db.delete(wh)
  await db.commit()


@router.post("/{webhook_id}/test", status_code=202)
async def test_webhook(
  webhook_id: uuid.UUID,
  background_tasks: BackgroundTasks,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> dict:
  wh = await _get_owned(db, webhook_id, current_user)
  background_tasks.add_task(
    dispatch_event,
    db,
    user_id=current_user.id,
    event_type="webhook.test",
    payload={"message": "This is a test delivery from Subconscious.", "webhook_id": str(wh.id)},
  )
  return {"status": "queued", "webhook_id": str(wh.id)}


@router.get("/{webhook_id}/deliveries", response_model=list[DeliveryResponse])
async def list_deliveries(
  webhook_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
  limit: int = Query(50, le=200),
) -> list[DeliveryResponse]:
  await _get_owned(db, webhook_id, current_user)
  result = await db.execute(
    select(WebhookDelivery)
    .where(WebhookDelivery.webhook_id == webhook_id)
    .order_by(WebhookDelivery.created_at.desc())
    .limit(limit)
  )
  return [
    DeliveryResponse(
      id=str(d.id),
      webhook_id=str(d.webhook_id),
      event_type=d.event_type,
      payload=d.payload_json,
      response_status=d.response_status,
      attempt_count=d.attempt_count,
      delivered_at=d.delivered_at,
      created_at=d.created_at,
    )
    for d in result.scalars()
  ]


@router.post("/{webhook_id}/rotate-secret", response_model=WebhookCreatedResponse)
async def rotate_secret(
  webhook_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> WebhookCreatedResponse:
  wh = await _get_owned(db, webhook_id, current_user)
  new_secret = generate_secret()
  wh.enc_secret = encrypt_token(new_secret)
  await db.commit()
  await db.refresh(wh)
  return _to_response(wh, reveal_secret=new_secret)  # type: ignore[return-value]


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_owned(db: AsyncSession, webhook_id: uuid.UUID, user: User) -> Webhook:
  result = await db.execute(
    select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
  )
  wh = result.scalar_one_or_none()
  if not wh:
    raise HTTPException(status_code=404, detail="Webhook not found")
  return wh

"""Auth business logic — upsert user/account, link providers."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import ApiKeyAccount, OAuthAccount, User
from app.services.token_service import decrypt_token, encrypt_token, mask_key


async def get_or_create_user(
  db: AsyncSession,
  *,
  email: str,
  display_name: str | None,
  avatar_url: str | None,
) -> User:
  result = await db.execute(select(User).where(User.email == email))
  user = result.scalar_one_or_none()
  if user is None:
    user = User(
      id=uuid.uuid4(),
      email=email,
      display_name=display_name,
      avatar_url=avatar_url,
    )
    db.add(user)
    await db.flush()
  return user


async def upsert_oauth_account(
  db: AsyncSession,
  *,
  user: User,
  provider_slug: str,
  provider_user_id: str,
  access_token: str,
  refresh_token: str | None,
  token_expires_at: "datetime | None",  # noqa: F821
  raw_profile: dict,
) -> OAuthAccount:
  result = await db.execute(
    select(OAuthAccount).where(
      OAuthAccount.provider_slug == provider_slug,
      OAuthAccount.provider_user_id == provider_user_id,
    )
  )
  account = result.scalar_one_or_none()
  if account is None:
    account = OAuthAccount(
      id=uuid.uuid4(),
      user_id=user.id,
      provider_slug=provider_slug,
      provider_user_id=provider_user_id,
    )
    db.add(account)

  account.enc_access_token = encrypt_token(access_token)
  account.enc_refresh_token = encrypt_token(refresh_token) if refresh_token else None
  account.token_expires_at = token_expires_at
  account.raw_profile_json = raw_profile
  await db.flush()
  return account


async def store_api_key(
  db: AsyncSession,
  *,
  user: User,
  provider_slug: str,
  api_key: str,
) -> ApiKeyAccount:
  result = await db.execute(
    select(ApiKeyAccount).where(
      ApiKeyAccount.user_id == user.id,
      ApiKeyAccount.provider_slug == provider_slug,
    )
  )
  account = result.scalar_one_or_none()
  if account is None:
    account = ApiKeyAccount(
      id=uuid.uuid4(),
      user_id=user.id,
      provider_slug=provider_slug,
    )
    db.add(account)

  account.enc_api_key = encrypt_token(api_key)
  account.key_hint = mask_key(api_key)
  await db.flush()
  return account


async def get_connected_provider_slugs(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
  oauth = await db.execute(
    select(OAuthAccount.provider_slug).where(OAuthAccount.user_id == user_id)
  )
  apikey = await db.execute(
    select(ApiKeyAccount.provider_slug).where(ApiKeyAccount.user_id == user_id)
  )
  return [r[0] for r in oauth.all()] + [r[0] for r in apikey.all()]

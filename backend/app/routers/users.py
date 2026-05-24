"""Users router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import ApiKeyAccount, OAuthAccount, User
from app.schemas.user import ConnectedProvider, UserProfile, UserUpdate
from app.services.provider_service import get_provider

router = APIRouter()


@router.get("/me", response_model=UserProfile)
async def get_profile(
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> UserProfile:
  oauth_res = await db.execute(
    select(OAuthAccount).where(OAuthAccount.user_id == current_user.id)
  )
  key_res = await db.execute(
    select(ApiKeyAccount).where(ApiKeyAccount.user_id == current_user.id)
  )

  connected: list[ConnectedProvider] = []
  for acc in oauth_res.scalars():
    meta = get_provider(acc.provider_slug)
    connected.append(ConnectedProvider(
      provider_slug=acc.provider_slug,
      auth_type="oauth2",
      display_name=meta.display_name if meta else acc.provider_slug,
      key_hint=None,
      linked_at=acc.linked_at,
    ))
  for acc in key_res.scalars():
    meta = get_provider(acc.provider_slug)
    connected.append(ConnectedProvider(
      provider_slug=acc.provider_slug,
      auth_type="apikey",
      display_name=meta.display_name if meta else acc.provider_slug,
      key_hint=acc.key_hint,
      linked_at=acc.created_at,
    ))

  return UserProfile(
    id=str(current_user.id),
    email=current_user.email,
    display_name=current_user.display_name,
    avatar_url=current_user.avatar_url,
    created_at=current_user.created_at,
    connected_providers=connected,
  )


@router.patch("/me", response_model=UserProfile)
async def update_profile(
  body: UserUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> UserProfile:
  if body.display_name is not None:
    current_user.display_name = body.display_name
  if body.avatar_url is not None:
    current_user.avatar_url = body.avatar_url
  await db.commit()
  await db.refresh(current_user)
  return await get_profile(db=db, current_user=current_user)


@router.delete("/me", status_code=204)
async def delete_account(
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
) -> None:
  from app.lmdb_client import revoke_all_user_tokens
  await revoke_all_user_tokens(str(current_user.id))
  await db.delete(current_user)
  await db.commit()

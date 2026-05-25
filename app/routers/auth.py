"""Auth router — OAuth login/callback, API key storage, session management."""
from __future__ import annotations

import secrets
import structlog
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request, Response, status

from app.config import get_settings
from app.database import get_db
from app.lmdb_client import consume_oauth_state, revoke_refresh_token, store_oauth_state
from app.schemas.auth import (
  ApiKeyRequest,
  ApiKeyResponse,
  AuthResponse,
  LoginInitResponse,
  ProviderInfo,
  TokenResponse,
  UserSummary,
)
from app.services.auth_service import (
  get_connected_provider_slugs,
  get_or_create_user,
  store_api_key,
  upsert_oauth_account,
)
from app.services.jwt_service import (
  create_access_token,
  create_refresh_token,
  rotate_refresh_token,
)
from app.services.provider_service import (
  build_oauth_client,
  get_active_providers,
  get_provider,
)
from app.middleware.auth_middleware import get_current_user

router = APIRouter()
settings = get_settings()
log = structlog.get_logger()

COOKIE_NAME = "sc_refresh"
COOKIE_MAX_AGE = settings.jwt_refresh_token_expire_days * 86400


# ── List providers ────────────────────────────────────────────────────────────

@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers(
  request: Request,
  db: AsyncSession = Depends(get_db),
) -> list[ProviderInfo]:
  current_user = None
  try:
    current_user = await get_current_user(request, db, required=False)
  except Exception:
    pass

  connected: set[str] = set()
  if current_user:
    connected = set(await get_connected_provider_slugs(db, current_user.id))

  return [
    ProviderInfo(
      slug=p.slug,
      display_name=p.display_name,
      icon_url=p.icon_url,
      auth_type=p.auth_type,
      is_connected=p.slug in connected,
    )
    for p in get_active_providers()
  ]


# ── OAuth login initiation ────────────────────────────────────────────────────

@router.get("/{slug}/login", response_model=None)
async def oauth_login(
  slug: str,
  request: Request,
  mode: str = Query("login", pattern="^(login|link)$"),
  native: bool = Query(False),
  code_challenge: str | None = Query(None),
  code_challenge_method: str | None = Query(None),
) -> RedirectResponse | LoginInitResponse:
  provider = get_provider(slug)
  if not provider or provider.auth_type != "oauth2":
    raise HTTPException(status_code=404, detail=f"OAuth provider '{slug}' not found")

  client = build_oauth_client(slug)
  if not client:
    raise HTTPException(status_code=503, detail=f"Provider '{slug}' not configured on this server")

  state = secrets.token_urlsafe(32)
  callback_url = f"{settings.oauth_callback_base}/auth/{slug}/callback"

  extra: dict = {}
  if slug == "google":
    extra["access_type"] = "offline"
    extra["prompt"] = "consent"
  if code_challenge:
    extra["code_challenge"] = code_challenge
    extra["code_challenge_method"] = code_challenge_method or "S256"

  url, _ = client.create_authorization_url(
    provider.authorization_endpoint,
    redirect_uri=callback_url,
    scope=" ".join(provider.scopes),
    state=state,
    **extra,
  )

  await store_oauth_state(state, {"slug": slug, "mode": mode})

  if native:
    return LoginInitResponse(url=url, state=state)
  return RedirectResponse(url, status_code=302)


# ── OAuth callback ────────────────────────────────────────────────────────────

@router.get("/{slug}/callback", response_model=None)
async def oauth_callback(
  slug: str,
  request: Request,
  response: Response,
  db: AsyncSession = Depends(get_db),
  code: str = Query(...),
  state: str = Query(...),
  code_verifier: str | None = Query(None),
) -> AuthResponse | RedirectResponse:
  # 1. Validate state
  state_data = await consume_oauth_state(state)
  if not state_data or state_data.get("slug") != slug:
    raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

  provider = get_provider(slug)
  client = build_oauth_client(slug)
  if not provider or not client:
    raise HTTPException(status_code=503, detail="Provider not available")

  callback_url = f"{settings.oauth_callback_base}/auth/{slug}/callback"

  # 2. Exchange code for tokens
  try:
    token_kwargs: dict = {"redirect_uri": callback_url}
    if code_verifier:
      token_kwargs["code_verifier"] = code_verifier
    token_data = await client.fetch_token(
      provider.token_endpoint,
      code=code,
      **token_kwargs,
    )
  except Exception as exc:
    log.error("oauth_token_exchange_failed", slug=slug, error=str(exc))
    raise HTTPException(status_code=502, detail="Token exchange failed")

  # 3. Fetch user profile
  try:
    client.token = token_data
    resp = await client.get(provider.userinfo_endpoint)
    resp.raise_for_status()
    raw_profile = resp.json()
  except Exception as exc:
    log.error("oauth_userinfo_failed", slug=slug, error=str(exc))
    raise HTTPException(status_code=502, detail="Failed to fetch user info")

  # 4. Normalise profile via provider adapter
  if not provider.extract_profile:
    raise HTTPException(status_code=500, detail="No profile extractor for this provider")
  profile = provider.extract_profile(raw_profile)

  # 5. Upsert user and account
  from datetime import UTC, datetime, timedelta
  expires_in = token_data.get("expires_in")
  expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None

  user = await get_or_create_user(
    db,
    email=profile["email"],
    display_name=profile.get("display_name"),
    avatar_url=profile.get("avatar_url"),
  )
  await upsert_oauth_account(
    db,
    user=user,
    provider_slug=slug,
    provider_user_id=profile["provider_user_id"],
    access_token=token_data["access_token"],
    refresh_token=token_data.get("refresh_token"),
    token_expires_at=expires_at,
    raw_profile=raw_profile,
  )
  await db.commit()

  # 6. Issue JWT + refresh token
  access_token, expires_seconds = create_access_token(str(user.id), user.email)
  refresh_jti = await create_refresh_token(str(user.id))
  connected = await get_connected_provider_slugs(db, user.id)

  auth_resp = AuthResponse(
    access_token=access_token,
    expires_in=expires_seconds,
    user=UserSummary(
      id=str(user.id),
      email=user.email,
      display_name=user.display_name,
      avatar_url=user.avatar_url,
      connected_providers=connected,
    ),
  )

  # Native: return JSON; Web: redirect with cookie
  is_native = request.query_params.get("native") == "true"
  if is_native:
    return auth_resp

  redirect_url = f"{settings.app_ui_base_url}?auth=success"
  redirect = RedirectResponse(redirect_url, status_code=302)
  redirect.set_cookie(
    COOKIE_NAME,
    refresh_jti,
    max_age=COOKIE_MAX_AGE,
    httponly=True,
    secure=settings.is_production,
    samesite="lax",
  )
  return redirect


# ── API key storage ───────────────────────────────────────────────────────────

@router.post("/apikey", response_model=ApiKeyResponse, status_code=201)
async def save_api_key(
  body: ApiKeyRequest,
  db: AsyncSession = Depends(get_db),
  current_user=Depends(get_current_user),
) -> ApiKeyResponse:
  provider = get_provider(body.provider_slug)
  if not provider or provider.auth_type != "apikey":
    raise HTTPException(status_code=404, detail="Unknown API-key provider")

  account = await store_api_key(
    db, user=current_user, provider_slug=body.provider_slug, api_key=body.api_key
  )
  await db.commit()
  return ApiKeyResponse(provider_slug=body.provider_slug, key_hint=account.key_hint)


# ── Disconnect a provider ─────────────────────────────────────────────────────

@router.delete("/{slug}/disconnect", status_code=204)
async def disconnect_provider(
  slug: str,
  db: AsyncSession = Depends(get_db),
  current_user=Depends(get_current_user),
) -> None:
  from sqlalchemy import delete
  from app.models.user import OAuthAccount, ApiKeyAccount

  await db.execute(
    delete(OAuthAccount).where(
      OAuthAccount.user_id == current_user.id,
      OAuthAccount.provider_slug == slug,
    )
  )
  await db.execute(
    delete(ApiKeyAccount).where(
      ApiKeyAccount.user_id == current_user.id,
      ApiKeyAccount.provider_slug == slug,
    )
  )
  await db.commit()


# ── Refresh access token ──────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
  sc_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
  if not sc_refresh:
    raise HTTPException(status_code=401, detail="No refresh token")

  result = await rotate_refresh_token(sc_refresh)
  if not result:
    raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

  user_id, _new_jti = result
  # We need email for JWT — load user from DB
  # (simplified: embed user_id only; full impl loads user)
  access_token, expires_in = create_access_token(user_id, "")

  response = JSONResponse(
    {"access_token": access_token, "token_type": "bearer", "expires_in": expires_in}
  )
  response.set_cookie(
    COOKIE_NAME,
    _new_jti,
    max_age=COOKIE_MAX_AGE,
    httponly=True,
    secure=settings.is_production,
    samesite="lax",
  )
  return response  # type: ignore[return-value]


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=204)
async def logout(
  response: Response,
  sc_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
  if sc_refresh:
    await revoke_refresh_token(sc_refresh)
  response.delete_cookie(COOKIE_NAME)


# ── Me (auth summary) ─────────────────────────────────────────────────────────

@router.get("/me", response_model=UserSummary)
async def auth_me(
  db: AsyncSession = Depends(get_db),
  current_user=Depends(get_current_user),
) -> UserSummary:
  connected = await get_connected_provider_slugs(db, current_user.id)
  return UserSummary(
    id=str(current_user.id),
    email=current_user.email,
    display_name=current_user.display_name,
    avatar_url=current_user.avatar_url,
    connected_providers=connected,
  )

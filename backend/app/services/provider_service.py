"""Provider registry — builds Authlib OAuth clients from settings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.config import get_settings

settings = get_settings()


@dataclass
class ProviderMeta:
  slug: str
  display_name: str
  icon_url: str
  auth_type: str                   # "oauth2" | "apikey"
  authorization_endpoint: str = ""
  token_endpoint: str = ""
  userinfo_endpoint: str = ""
  scopes: list[str] = field(default_factory=list)
  # Callable to extract normalised profile from raw userinfo JSON
  extract_profile: Callable[[dict], dict] | None = None


def _google_profile(raw: dict) -> dict:
  return {
    "provider_user_id": raw["sub"],
    "email": raw.get("email", ""),
    "display_name": raw.get("name"),
    "avatar_url": raw.get("picture"),
  }


def _microsoft_profile(raw: dict) -> dict:
  return {
    "provider_user_id": raw["sub"] or raw.get("oid", ""),
    "email": raw.get("email") or raw.get("preferred_username", ""),
    "display_name": raw.get("name"),
    "avatar_url": None,
  }


def _github_profile(raw: dict) -> dict:
  return {
    "provider_user_id": str(raw["id"]),
    "email": raw.get("email", ""),
    "display_name": raw.get("name") or raw.get("login"),
    "avatar_url": raw.get("avatar_url"),
  }


def _openai_profile(raw: dict) -> dict:
  return {
    "provider_user_id": raw.get("id") or raw.get("sub", ""),
    "email": raw.get("email", ""),
    "display_name": raw.get("name"),
    "avatar_url": raw.get("picture"),
  }


def _huggingface_profile(raw: dict) -> dict:
  return {
    "provider_user_id": raw.get("id") or raw.get("sub", ""),
    "email": raw.get("email", ""),
    "display_name": raw.get("name") or raw.get("preferred_username"),
    "avatar_url": raw.get("avatarUrl"),
  }


def _discord_profile(raw: dict) -> dict:
  uid = str(raw["id"])
  avatar_hash = raw.get("avatar")
  avatar = f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png" if avatar_hash else None
  return {
    "provider_user_id": uid,
    "email": raw.get("email", ""),
    "display_name": raw.get("global_name") or raw.get("username"),
    "avatar_url": avatar,
  }


# ── Registry ─────────────────────────────────────────────────────────────────

_PROVIDER_DEFS: list[ProviderMeta] = [
  ProviderMeta(
    slug="google",
    display_name="Google",
    icon_url="https://cdn.subconscious.chat/icons/google.svg",
    auth_type="oauth2",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
    scopes=["openid", "email", "profile"],
    extract_profile=_google_profile,
  ),
  ProviderMeta(
    slug="microsoft",
    display_name="Microsoft",
    icon_url="https://cdn.subconscious.chat/icons/microsoft.svg",
    auth_type="oauth2",
    authorization_endpoint=f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/authorize",
    token_endpoint=f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/token",
    userinfo_endpoint="https://graph.microsoft.com/oidc/userinfo",
    scopes=["openid", "email", "profile", "offline_access"],
    extract_profile=_microsoft_profile,
  ),
  ProviderMeta(
    slug="openai",
    display_name="ChatGPT / OpenAI",
    icon_url="https://cdn.subconscious.chat/icons/openai.svg",
    auth_type="oauth2",
    authorization_endpoint="https://auth.openai.com/authorize",
    token_endpoint="https://auth.openai.com/oauth/token",
    userinfo_endpoint="https://api.openai.com/v1/me",
    scopes=["openid", "email", "profile"],
    extract_profile=_openai_profile,
  ),
  ProviderMeta(
    slug="github",
    display_name="GitHub",
    icon_url="https://cdn.subconscious.chat/icons/github.svg",
    auth_type="oauth2",
    authorization_endpoint="https://github.com/login/oauth/authorize",
    token_endpoint="https://github.com/login/oauth/access_token",
    userinfo_endpoint="https://api.github.com/user",
    scopes=["read:user", "user:email"],
    extract_profile=_github_profile,
  ),
  ProviderMeta(
    slug="huggingface",
    display_name="Hugging Face",
    icon_url="https://cdn.subconscious.chat/icons/huggingface.svg",
    auth_type="oauth2",
    authorization_endpoint="https://huggingface.co/oauth/authorize",
    token_endpoint="https://huggingface.co/oauth/token",
    userinfo_endpoint="https://huggingface.co/oauth/userinfo",
    scopes=["openid", "email", "profile"],
    extract_profile=_huggingface_profile,
  ),
  ProviderMeta(
    slug="discord",
    display_name="Discord",
    icon_url="https://cdn.subconscious.chat/icons/discord.svg",
    auth_type="oauth2",
    authorization_endpoint="https://discord.com/oauth2/authorize",
    token_endpoint="https://discord.com/api/oauth2/token",
    userinfo_endpoint="https://discord.com/api/users/@me",
    scopes=["identify", "email"],
    extract_profile=_discord_profile,
  ),
  # ── API-key-only providers ─────────────────────────────────────────────
  ProviderMeta(
    slug="anthropic",
    display_name="Claude / Anthropic",
    icon_url="https://cdn.subconscious.chat/icons/anthropic.svg",
    auth_type="apikey",
  ),
  ProviderMeta(
    slug="deepseek",
    display_name="DeepSeek",
    icon_url="https://cdn.subconscious.chat/icons/deepseek.svg",
    auth_type="apikey",
  ),
  ProviderMeta(
    slug="ollama",
    display_name="Ollama (local)",
    icon_url="https://cdn.subconscious.chat/icons/ollama.svg",
    auth_type="apikey",
  ),
]


def _has_credentials(slug: str) -> bool:
  """Check whether client_id/secret are configured for an OAuth provider."""
  cfg = settings
  mapping = {
    "google": cfg.google_client_id,
    "microsoft": cfg.microsoft_client_id,
    "openai": cfg.openai_client_id,
    "github": cfg.github_client_id,
    "huggingface": cfg.huggingface_client_id,
    "discord": cfg.discord_client_id,
  }
  return bool(mapping.get(slug))


def get_active_providers() -> list[ProviderMeta]:
  """Return providers that are configured (or are apikey-type, always available)."""
  return [
    p for p in _PROVIDER_DEFS
    if p.auth_type == "apikey" or _has_credentials(p.slug)
  ]


def get_provider(slug: str) -> ProviderMeta | None:
  return next((p for p in _PROVIDER_DEFS if p.slug == slug), None)


def get_client_credentials(slug: str) -> tuple[str, str] | None:
  """Return (client_id, client_secret) for a given provider slug, or None."""
  cfg = settings
  creds: dict[str, tuple[str | None, str | None]] = {
    "google": (cfg.google_client_id, cfg.google_client_secret),
    "microsoft": (cfg.microsoft_client_id, cfg.microsoft_client_secret),
    "openai": (cfg.openai_client_id, cfg.openai_client_secret),
    "github": (cfg.github_client_id, cfg.github_client_secret),
    "huggingface": (cfg.huggingface_client_id, cfg.huggingface_client_secret),
    "discord": (cfg.discord_client_id, cfg.discord_client_secret),
  }
  pair = creds.get(slug)
  if pair and pair[0] and pair[1]:
    return (pair[0], pair[1])  # type: ignore[return-value]
  return None


def build_oauth_client(slug: str) -> AsyncOAuth2Client | None:
  creds = get_client_credentials(slug)
  if not creds:
    return None
  client_id, client_secret = creds
  return AsyncOAuth2Client(
    client_id=client_id,
    client_secret=client_secret,
  )

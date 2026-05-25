"""
Application configuration — reads from environment / .env file.
All secrets must come from env vars; never hardcode.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
  )

  # ── App ─────────────────────────────────────────────────────────────────
  app_env: Literal["development", "staging", "production"] = "development"
  app_version: str = "0.1.0"
  app_secret_key: str = Field(..., min_length=32)

  # Canonical public URLs
  web_base_url: AnyHttpUrl = AnyHttpUrl("https://subconscious.chat")
  app_base_url: AnyHttpUrl = AnyHttpUrl("https://api.subconscious.chat")
  docs_base_url: AnyHttpUrl = AnyHttpUrl("https://docs.subconscious.chat")
  app_ui_base_url: AnyHttpUrl = AnyHttpUrl("https://app.subconscious.chat")

  # ── Data directory (SQLite + LMDB placed together for single-container)
  # Both the SQLite file and LMDB environment live under `./data` by
  # default so they are colocated inside the container.
  data_dir: str = "./data"

  # SQLite database URL (file inside `data_dir`)
  database_url: str = "sqlite+aiosqlite:///./data/subconscious.db"

  # LMDB environment path (parent directory is `data_dir`)
  lmdb_path: str = "./data"
  lmdb_map_size: int = 1073741824  # 1 GiB

  # ── Token encryption (Fernet) ────────────────────────────────────────────
  token_encryption_key: str = Field(..., min_length=44)          # base64 Fernet key
  token_encryption_key_old: str | None = None                    # for rotation

  # ── JWT ──────────────────────────────────────────────────────────────────
  jwt_secret_key: str = Field(..., min_length=32)
  jwt_algorithm: str = "HS256"
  jwt_access_token_expire_minutes: int = 15
  jwt_refresh_token_expire_days: int = 30

  # ── CORS ─────────────────────────────────────────────────────────────────
  cors_allowed_origins: list[str] = [
    "http://localhost:3000",
    "http://localhost:8550",
    "https://subconscious.chat",
    "https://app.subconscious.chat",
    "https://docs.subconscious.chat",
  ]

  # ── OAuth providers (all optional — provider hidden if client_id missing) ─
  google_client_id: str | None = None
  google_client_secret: str | None = None

  microsoft_client_id: str | None = None
  microsoft_client_secret: str | None = None
  microsoft_tenant_id: str = "common"

  openai_client_id: str | None = None
  openai_client_secret: str | None = None

  github_client_id: str | None = None
  github_client_secret: str | None = None

  huggingface_client_id: str | None = None
  huggingface_client_secret: str | None = None

  discord_client_id: str | None = None
  discord_client_secret: str | None = None

  # ── Webhook delivery ─────────────────────────────────────────────────────
  webhook_max_retries: int = 5
  webhook_retry_backoff_base: int = 2    # seconds; delay = base ** attempt
  webhook_delivery_timeout: int = 10     # seconds per HTTP attempt

  # ── Rate limiting ────────────────────────────────────────────────────────
  rate_limit_auth: str = "20/minute"
  rate_limit_api: str = "200/minute"

  # ── Derived helpers ───────────────────────────────────────────────────────
  @property
  def is_production(self) -> bool:
    return self.app_env == "production"

  @property
  def oauth_callback_base(self) -> str:
    return str(self.app_base_url).rstrip("/")

  @field_validator("cors_allowed_origins", mode="before")
  @classmethod
  def split_cors(cls, v: str | list[str]) -> list[str]:
    if isinstance(v, str):
      return [o.strip() for o in v.split(",") if o.strip()]
    return v


@lru_cache
def get_settings() -> Settings:
  return Settings()  # type: ignore[call-arg]

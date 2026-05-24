"""ORM models — User, OAuthAccount, ApiKeyAccount."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func, JSON, ForeignKey, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GUID(TypeDecorator):
    """ Platform-independent GUID type.
        Uses PostgreSQL's UUID type, otherwise uses String.
    """
    impl = PG_UUID
    cache_ok = True

    def load_dialect_impl(self, dialect):
      if dialect.name == 'postgresql':
        return dialect.type_descriptor(PG_UUID(as_uuid=True))
      else:
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
      if value is None:
        return value
      elif dialect.name == 'postgresql':
        return str(value)
      else:
        if not isinstance(value, uuid.UUID):
          return str(uuid.UUID(value))
        else:
          return str(value)

    def process_result_value(self, value, dialect):
      if value is None:
        return value
      else:
        if not isinstance(value, uuid.UUID):
          return uuid.UUID(value)
        else:
          return value


class User(Base):
  __tablename__ = "user"

  id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
  email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
  display_name: Mapped[str | None] = mapped_column(String(200))
  avatar_url: Mapped[str | None] = mapped_column(Text)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
  )

  # relationships
  oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
    "OAuthAccount", back_populates="user", cascade="all, delete-orphan"
  )
  api_key_accounts: Mapped[list[ApiKeyAccount]] = relationship(
    "ApiKeyAccount", back_populates="user", cascade="all, delete-orphan"
  )
  webhooks: Mapped[list["Webhook"]] = relationship(  # noqa: F821
    "Webhook", back_populates="user", cascade="all, delete-orphan"
  )


class OAuthAccount(Base):
  __tablename__ = "oauth_account"

  id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
  user_id: Mapped[uuid.UUID] = mapped_column(
    GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
  )
  provider_slug: Mapped[str] = mapped_column(String(64), nullable=False)
  provider_user_id: Mapped[str] = mapped_column(String(256), nullable=False)
  enc_access_token: Mapped[bytes | None] = mapped_column(Text)   # Fernet-encrypted, stored as str
  enc_refresh_token: Mapped[bytes | None] = mapped_column(Text)
  token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
  raw_profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
  linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

  user: Mapped[User] = relationship("User", back_populates="oauth_accounts")

  __table_args__ = (
    # One account per provider per provider_user_id
    __import__("sqlalchemy").UniqueConstraint(
        "provider_slug", "provider_user_id", name="uq_oauth_provider_uid"
    ),
  )


class ApiKeyAccount(Base):
  """Stores encrypted API keys for providers that don't support OAuth (Anthropic, DeepSeek, etc.)."""

  __tablename__ = "api_key_account"

  id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
  user_id: Mapped[uuid.UUID] = mapped_column(
    GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
  )
  provider_slug: Mapped[str] = mapped_column(String(64), nullable=False)
  enc_api_key: Mapped[str] = mapped_column(Text, nullable=False)   # Fernet-encrypted
  key_hint: Mapped[str] = mapped_column(String(16), nullable=False)  # last 4 chars shown in UI
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
  )

  user: Mapped[User] = relationship("User", back_populates="api_key_accounts")

  __table_args__ = (
    __import__("sqlalchemy").UniqueConstraint(
      "user_id", "provider_slug", name="uq_apikey_user_provider"
    ),
  )

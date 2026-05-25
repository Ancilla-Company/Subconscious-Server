"""Token encryption/decryption service using Fernet (AES-128-CBC + HMAC-SHA256).

Supports key rotation via MultiFernet: the primary key is used for encryption;
old keys are tried in order for decryption.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

from app.config import get_settings

_fernet: MultiFernet | None = None


def _get_fernet() -> MultiFernet:
  global _fernet
  if _fernet is None:
    settings = get_settings()
    keys = [Fernet(settings.token_encryption_key.encode())]
    if settings.token_encryption_key_old:
      keys.append(Fernet(settings.token_encryption_key_old.encode()))
    _fernet = MultiFernet(keys)
  return _fernet


def encrypt_token(plaintext: str) -> str:
  """Encrypt a plaintext token and return a base64 Fernet token string."""
  f = _get_fernet()
  return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
  """Decrypt a Fernet-encrypted token string. Raises InvalidToken on failure."""
  f = _get_fernet()
  return f.decrypt(ciphertext.encode()).decode()


def mask_key(key: str, visible_chars: int = 4) -> str:
  """Return a masked version of a key for display (e.g. '...8f3c')."""
  if len(key) <= visible_chars:
    return "*" * len(key)
  return "..." + key[-visible_chars:]

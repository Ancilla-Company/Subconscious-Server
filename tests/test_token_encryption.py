"""Tests for token encryption service."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.services.token_service import decrypt_token, encrypt_token, mask_key


def test_roundtrip(monkeypatch, fernet_key):
  monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", fernet_key)
  # Reload singleton
  import app.services.token_service as ts
  ts._fernet = None

  plaintext = "sk-ant-api03-supersecretkeyvalue"
  ciphertext = encrypt_token(plaintext)
  assert ciphertext != plaintext
  assert decrypt_token(ciphertext) == plaintext


def test_mask_key():
  assert mask_key("sk-ant-api03-abc1234") == "...1234"
  assert mask_key("abcd") == "****"
  assert mask_key("abc") == "***"
  assert mask_key("ab") == "**"


def test_invalid_token_raises(monkeypatch, fernet_key):
  monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", fernet_key)
  import app.services.token_service as ts
  ts._fernet = None

  with pytest.raises(InvalidToken):
    decrypt_token("not-valid-fernet-token")

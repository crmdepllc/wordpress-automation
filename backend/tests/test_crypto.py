"""Unit tests for credential encryption."""

from __future__ import annotations

import pytest

from app import crypto
from app.config import get_settings
from app.crypto import EncryptionKeyMissingError, decrypt, encrypt


def test_encrypt_decrypt_roundtrip():
    secret = "hunter2-app-password"
    token = encrypt(secret)
    assert token != secret  # actually encrypted
    assert decrypt(token) == secret


def test_ciphertext_is_nondeterministic():
    # Fernet includes a random IV + timestamp, so two encryptions differ.
    assert encrypt("same") != encrypt("same")


def test_missing_key_raises(monkeypatch, fresh_caches):
    settings = get_settings()
    monkeypatch.setattr(settings, "credential_encryption_key", "", raising=False)
    crypto._fernet.cache_clear()
    with pytest.raises(EncryptionKeyMissingError):
        encrypt("anything")

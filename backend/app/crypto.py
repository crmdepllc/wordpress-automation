"""Symmetric encryption for credentials at rest.

Uses Fernet (AES-128-CBC + HMAC) with the key from
``settings.credential_encryption_key``. The key is NEVER hardcoded — it comes
from the environment / ``.env``. If a credential operation runs without a key,
we raise a clear error rather than silently storing plaintext (AGENTS.md rule:
never commit/store secrets in plaintext).
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


class EncryptionKeyMissingError(RuntimeError):
    """Raised when an encrypt/decrypt is attempted with no key configured."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().credential_encryption_key
    if not key:
        raise EncryptionKeyMissingError(
            "CREDENTIAL_ENCRYPTION_KEY is not set. Generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and add it to backend/.env.'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning a URL-safe token."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`."""
    return _fernet().decrypt(token.encode()).decode()

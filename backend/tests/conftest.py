"""Shared test setup.

Sets a throwaway encryption key in the environment BEFORE any app module is
imported, so the Fernet-backed credential code has a key to work with. This key
is generated per test run and never written anywhere — no secret is committed.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

# Must run before `app.config` is imported by any test module.
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ANTHROPIC_API_KEY", "")

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.crypto import _fernet  # noqa: E402

# Caches were created (if at all) with whatever env existed at import; clear so
# they pick up the test key.
get_settings.cache_clear()
_fernet.cache_clear()


@pytest.fixture
def fresh_caches():
    """Reset cached settings/Fernet around a test that mutates config."""
    get_settings.cache_clear()
    _fernet.cache_clear()
    yield
    get_settings.cache_clear()
    _fernet.cache_clear()

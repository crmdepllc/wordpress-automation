"""Declarative base and a Fernet-encrypted string column type."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.crypto import decrypt, encrypt


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class EncryptedString(TypeDecorator[str]):
    """A String column transparently encrypted at rest with Fernet.

    Values are encrypted on the way into the database and decrypted on the way
    out, so the plaintext never touches disk. Backed by ``Text`` because the
    Fernet token is longer than the original value.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return encrypt(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return decrypt(value)

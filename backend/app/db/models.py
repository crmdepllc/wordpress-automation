"""ORM models.

``WpSite`` stores the connection details for one WordPress site the agent can
manage. Secret fields (Application Password, SSH user/key) use
``EncryptedString`` so they are encrypted at rest. Multiple sites are supported
— one row each, addressed by ``slug``.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EncryptedString


class WpCliTransport(str, enum.Enum):
    """How WP-CLI commands reach this site."""

    ssh = "ssh"  # real remote site (Fabric/Paramiko)
    local_docker = "local_docker"  # local sandbox (docker exec)


class WpSite(Base):
    __tablename__ = "wp_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str] = mapped_column(String(512))

    # WP REST API auth (Application Passwords).
    wp_username: Mapped[str] = mapped_column(String(255))
    wp_app_password: Mapped[str] = mapped_column(EncryptedString)

    # WP-CLI transport + (encrypted) SSH connection details for ssh transport.
    wpcli_transport: Mapped[WpCliTransport] = mapped_column(
        Enum(WpCliTransport, name="wpcli_transport"),
        default=WpCliTransport.ssh,
    )
    ssh_host: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    ssh_private_key: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # WP-CLI path on the remote host / container (e.g. "wp" or an absolute path).
    wp_cli_path: Mapped[str] = mapped_column(String(255), default="wp")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

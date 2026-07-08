"""ORM models.

``WpSite`` stores the connection details for one WordPress site the agent can
manage. Secret fields (Application Password, SSH user/key) use
``EncryptedString`` so they are encrypted at rest. Multiple sites are supported
— one row each, addressed by ``slug``.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EncryptedString


class WpCliTransport(str, enum.Enum):
    """How WP-CLI commands reach this site."""

    ssh = "ssh"  # real remote site (Fabric/Paramiko)
    local_docker = "local_docker"  # local sandbox (docker exec)
    local_process = "local_process"  # locally-installed dev site (e.g. Local by WP Engine)


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

    # local_process transport only: working directory to run WP-CLI from (the
    # site's public/ dir) and extra environment variables it needs (e.g. a
    # bundled PHP's PHPRC, a PATH prefix for its binaries). JSON-encoded dict;
    # not secret (paths/config, no credentials), so stored as plain text.
    cli_cwd: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cli_env: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Task(Base):
    """An orchestration run. ``id`` doubles as the LangGraph checkpoint thread id,
    so a paused (interrupted) task can be re-found and resumed after a restart."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    site_slug: Mapped[str] = mapped_column(String(64), index=True)
    instruction: Mapped[str] = mapped_column(Text)
    # planning | awaiting_approval | executing | completed | rejected | error
    status: Mapped[str] = mapped_column(String(32), default="planning")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

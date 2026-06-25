"""Typed models for WordPress integration.

These cover the connection credentials and the subset of WP entities the agent
reads/writes in Sprint 3 (posts, pages, media, menus). WP's REST API returns
some fields as ``{"rendered": "..."}`` objects; the parsers here flatten those
to plain strings.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Connection ----------------------------------------------------------


class SiteCredentials(BaseModel):
    """Everything needed to talk to one WordPress site (decrypted)."""

    slug: str
    base_url: str
    wp_username: str
    wp_app_password: str
    wpcli_transport: Literal["ssh", "local_docker"] = "ssh"
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_user: str | None = None
    ssh_private_key: str | None = None
    wp_cli_path: str = "wp"


# --- REST entities -------------------------------------------------------


def _rendered(value: Any) -> str:
    """Flatten WP's {"rendered": "..."} shape (or pass a plain string)."""
    if isinstance(value, dict):
        return str(value.get("rendered", ""))
    return "" if value is None else str(value)


class ContentItem(BaseModel):
    """A post or page returned by the REST API."""

    id: int
    title: str
    status: str
    slug: str = ""
    link: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ContentItem":
        return cls(
            id=int(data["id"]),
            title=_rendered(data.get("title")),
            status=str(data.get("status", "")),
            slug=str(data.get("slug", "")),
            link=str(data.get("link", "")),
        )


class ContentCreate(BaseModel):
    """Payload to create a post/page."""

    title: str
    content: str = ""
    status: Literal["draft", "publish", "pending", "private"] = "draft"
    slug: str | None = None

    def to_api(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "title": self.title,
            "content": self.content,
            "status": self.status,
        }
        if self.slug:
            body["slug"] = self.slug
        return body


class ContentUpdate(BaseModel):
    """Partial update for a post/page."""

    title: str | None = None
    content: str | None = None
    status: Literal["draft", "publish", "pending", "private"] | None = None

    def to_api(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class MediaItem(BaseModel):
    id: int
    source_url: str = ""
    mime_type: str = ""
    title: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "MediaItem":
        return cls(
            id=int(data["id"]),
            source_url=str(data.get("source_url", "")),
            mime_type=str(data.get("mime_type", "")),
            title=_rendered(data.get("title")),
        )


class MenuItem(BaseModel):
    id: int
    name: str = ""
    slug: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "MenuItem":
        return cls(
            id=int(data["id"]),
            name=str(data.get("name", "")),
            slug=str(data.get("slug", "")),
        )


# --- WP-CLI --------------------------------------------------------------


class CliResult(BaseModel):
    """Result of a WP-CLI command."""

    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

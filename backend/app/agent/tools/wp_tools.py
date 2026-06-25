"""WordPress capabilities as typed LangChain/LangGraph tools.

Design rules baked in here:
  - Every tool has an explicit typed signature (its schema) and returns a
    JSON-serializable dict (its structured output).
  - Read tools run freely. **Write tools refuse to act unless ``approved`` is
    True**, returning a ``needs_approval`` preview instead — this is the
    code-level enforcement of the human approval gate until Sprint 4 wires the
    real LangGraph interrupt.
  - Content (pages/posts/menus/media) goes through the REST API; plugin
    install/activate and Elementor CSS flush go through WP-CLI.
  - Every call and its result are logged.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from app.db.session import get_sessionmaker
from app.wp.credentials import get_site_credentials
from app.wp.rest_client import WordPressRestClient
from app.wp.schemas import ContentCreate, ContentUpdate, SiteCredentials
from app.wp.wpcli import WpCli

logger = logging.getLogger("agent.tools")


async def _credentials(site_slug: str) -> SiteCredentials:
    async with get_sessionmaker()() as session:
        return await get_site_credentials(session, site_slug)


def _needs_approval(action: str, preview: dict[str, Any]) -> dict[str, Any]:
    """Standard response when a write is attempted without approval."""
    logger.info("tool gated (needs approval): %s %s", action, preview)
    return {
        "status": "needs_approval",
        "action": action,
        "preview": preview,
        "message": (
            f"This will modify the live site ({action}). "
            "Re-invoke with approved=True to apply."
        ),
    }


# --- Read tools (ungated) ------------------------------------------------


@tool
async def wp_list_pages(site_slug: str, per_page: int = 20) -> dict[str, Any]:
    """List pages on a WordPress site. Read-only."""
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        pages = await wp.list_pages(per_page=per_page)
    logger.info("wp_list_pages(%s) -> %d pages", site_slug, len(pages))
    return {"status": "ok", "pages": [p.model_dump() for p in pages]}


@tool
async def wp_get_page(site_slug: str, page_id: int) -> dict[str, Any]:
    """Fetch a single page by id. Read-only."""
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        page = await wp.get_page(page_id)
    return {"status": "ok", "page": page.model_dump()}


@tool
async def wp_list_posts(site_slug: str, per_page: int = 20) -> dict[str, Any]:
    """List posts on a WordPress site. Read-only."""
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        posts = await wp.list_posts(per_page=per_page)
    return {"status": "ok", "posts": [p.model_dump() for p in posts]}


@tool
async def wp_list_menus(site_slug: str) -> dict[str, Any]:
    """List navigation menus on a WordPress site. Read-only."""
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        menus = await wp.list_menus()
    return {"status": "ok", "menus": [m.model_dump() for m in menus]}


# --- Write tools (gated on `approved`) -----------------------------------


@tool
async def wp_create_page(
    site_slug: str,
    title: str,
    content: str = "",
    status: str = "draft",
    approved: bool = False,
) -> dict[str, Any]:
    """Create a page. WRITE — requires approved=True to apply."""
    preview = {"site": site_slug, "title": title, "status": status}
    if not approved:
        return _needs_approval("create page", preview)
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        page = await wp.create_page(
            ContentCreate(title=title, content=content, status=status)  # type: ignore[arg-type]
        )
    logger.info("wp_create_page(%s) -> id=%s", site_slug, page.id)
    return {"status": "applied", "page": page.model_dump()}


@tool
async def wp_update_page(
    site_slug: str,
    page_id: int,
    title: str | None = None,
    content: str | None = None,
    status: str | None = None,
    approved: bool = False,
) -> dict[str, Any]:
    """Update a page. WRITE — requires approved=True to apply."""
    preview = {"site": site_slug, "page_id": page_id, "title": title, "status": status}
    if not approved:
        return _needs_approval("update page", preview)
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        page = await wp.update_page(
            page_id,
            ContentUpdate(title=title, content=content, status=status),  # type: ignore[arg-type]
        )
    return {"status": "applied", "page": page.model_dump()}


@tool
async def wp_delete_page(
    site_slug: str, page_id: int, force: bool = False, approved: bool = False
) -> dict[str, Any]:
    """Delete (or trash) a page. WRITE — requires approved=True to apply."""
    preview = {"site": site_slug, "page_id": page_id, "force": force}
    if not approved:
        return _needs_approval("delete page", preview)
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        await wp.delete_page(page_id, force=force)
    return {"status": "applied", "deleted_page_id": page_id}


@tool
async def wp_create_post(
    site_slug: str,
    title: str,
    content: str = "",
    status: str = "draft",
    approved: bool = False,
) -> dict[str, Any]:
    """Create a post. WRITE — requires approved=True to apply."""
    preview = {"site": site_slug, "title": title, "status": status}
    if not approved:
        return _needs_approval("create post", preview)
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        post = await wp.create_post(
            ContentCreate(title=title, content=content, status=status)  # type: ignore[arg-type]
        )
    return {"status": "applied", "post": post.model_dump()}


@tool
async def wp_install_plugin(
    site_slug: str, plugin_slug: str, activate: bool = True, approved: bool = False
) -> dict[str, Any]:
    """Install (and optionally activate) a plugin via WP-CLI. WRITE — requires approved=True."""
    preview = {"site": site_slug, "plugin": plugin_slug, "activate": activate}
    if not approved:
        return _needs_approval("install plugin", preview)
    creds = await _credentials(site_slug)
    result = await WpCli.from_credentials(creds).install_plugin(
        plugin_slug, activate=activate
    )
    logger.info("wp_install_plugin(%s, %s) -> exit=%s", site_slug, plugin_slug, result.exit_code)
    return {"status": "applied" if result.ok else "error", "result": result.model_dump()}


@tool
async def wp_activate_plugin(
    site_slug: str, plugin_slug: str, approved: bool = False
) -> dict[str, Any]:
    """Activate an installed plugin via WP-CLI. WRITE — requires approved=True."""
    preview = {"site": site_slug, "plugin": plugin_slug}
    if not approved:
        return _needs_approval("activate plugin", preview)
    creds = await _credentials(site_slug)
    result = await WpCli.from_credentials(creds).activate_plugin(plugin_slug)
    return {"status": "applied" if result.ok else "error", "result": result.model_dump()}


@tool
async def wp_flush_elementor_css(site_slug: str, approved: bool = False) -> dict[str, Any]:
    """Regenerate Elementor CSS via WP-CLI. WRITE — requires approved=True."""
    if not approved:
        return _needs_approval("flush Elementor CSS", {"site": site_slug})
    creds = await _credentials(site_slug)
    result = await WpCli.from_credentials(creds).flush_css()
    return {"status": "applied" if result.ok else "error", "result": result.model_dump()}


READ_TOOLS = [wp_list_pages, wp_get_page, wp_list_posts, wp_list_menus]
WRITE_TOOLS = [
    wp_create_page,
    wp_update_page,
    wp_delete_page,
    wp_create_post,
    wp_install_plugin,
    wp_activate_plugin,
    wp_flush_elementor_css,
]
WP_TOOLS = [*READ_TOOLS, *WRITE_TOOLS]

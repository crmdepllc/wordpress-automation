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


@tool
async def wp_create_elementor_page(
    site_slug: str, brief: str, status: str = "draft", approved: bool = False
) -> dict[str, Any]:
    """Generate an Elementor landing page from a plain-language brief and publish it.

    Generates a validated layout, writes it via REST, then regenerates Elementor
    CSS. WRITE — requires approved=True.
    """
    if not approved:
        return _needs_approval("create Elementor page", {"site": site_slug, "brief": brief})

    # Import here so the tools module doesn't pull the skill (and its model deps)
    # unless this tool actually runs.
    from app.agent.skills.elementor import ElementorValidationError, generate_elementor_page

    try:
        page_spec = await generate_elementor_page(brief)
    except ElementorValidationError as exc:
        # Never write invalid Elementor data.
        return {"status": "error", "stage": "validation", "errors": exc.errors}

    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        page = await wp.create_elementor_page(
            page_spec["title"], page_spec["elementor_data"], status=status
        )
    # A layout write is incomplete until CSS is regenerated (integration rule).
    flush = await WpCli.from_credentials(creds).flush_css()
    logger.info(
        "wp_create_elementor_page(%s) -> page=%s sections=%s flushed=%s",
        site_slug, page.id, page_spec["sections"], flush.ok,
    )
    return {
        "status": "applied",
        "page": page.model_dump(),
        "sections": page_spec["sections"],
        "css_flushed": flush.ok,
    }


# --- Sprint 6 skills: content / SEO / theming / plugins -----------------


@tool
async def wp_publish_post(
    site_slug: str,
    brief: str,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
    status: str = "draft",
    publish_at: str | None = None,
    approved: bool = False,
) -> dict[str, Any]:
    """Draft a blog post from a brief, assign categories/tags (created if missing),
    and publish or schedule it. WRITE — requires approved=True."""
    if not approved:
        return _needs_approval(
            "publish post", {"site": site_slug, "brief": brief, "status": status}
        )
    from app.agent.skills.content import generate_post_draft

    draft = await generate_post_draft(brief)
    cat_names = list(dict.fromkeys([*(categories or []), *draft.categories]))
    tag_names = list(dict.fromkeys([*(tags or []), *draft.tags]))

    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        cat_ids = await wp.ensure_categories(cat_names)
        tag_ids = await wp.ensure_tags(tag_names)
        post = await wp.create_post(
            ContentCreate(
                title=draft.title,
                content=draft.content,
                status="future" if publish_at else status,  # type: ignore[arg-type]
                categories=cat_ids,
                tags=tag_ids,
                date=publish_at,
            )
        )
    logger.info("wp_publish_post(%s) -> id=%s", site_slug, post.id)
    return {
        "status": "applied",
        "post": post.model_dump(),
        "categories": cat_names,
        "tags": tag_names,
        "scheduled_for": publish_at,
    }


@tool
async def wp_apply_seo(
    site_slug: str,
    target_id: int | str,
    subject: str,
    target_type: str = "post",
    provider: str = "yoast",
    approved: bool = False,
) -> dict[str, Any]:
    """Generate an SEO title/description + JSON-LD for a page/post and write it
    as provider (Yoast/RankMath) meta. WRITE — requires approved=True."""
    if not approved:
        return _needs_approval(
            "apply SEO", {"site": site_slug, "target": f"{target_type}:{target_id}"}
        )
    from app.agent.skills.seo import generate_seo, seo_to_meta

    creds = await _credentials(site_slug)
    seo = await generate_seo(subject)
    resource = "pages" if target_type == "page" else "posts"
    async with WordPressRestClient.from_credentials(creds) as wp:
        item = (
            await wp.get_page(target_id)
            if target_type == "page"
            else await wp.get_post(target_id)
        )
        meta = seo_to_meta(
            seo, provider=provider, name=item.title, url=item.link or creds.base_url
        )
        await wp.update_content_meta(resource, target_id, meta)
    return {"status": "applied", "seo": seo.model_dump(), "meta_keys": list(meta)}


@tool
async def wp_apply_theme(
    site_slug: str, brief: str, approved: bool = False
) -> dict[str, Any]:
    """Generate a theme (palette, fonts, footer) from a brief and apply it via
    WP-CLI theme mods + the Elementor global kit. WRITE — requires approved=True."""
    if not approved:
        return _needs_approval("apply theme", {"site": site_slug, "brief": brief})
    from app.agent.skills.theme import apply_theme, generate_theme

    creds = await _credentials(site_slug)
    spec = await generate_theme(brief)
    results = await apply_theme(WpCli.from_credentials(creds), spec)
    logger.info("wp_apply_theme(%s) -> %d steps", site_slug, len(results))
    return {"status": "applied", "theme": spec.model_dump(), "results": results}


@tool
async def wp_search_plugins(site_slug: str, query: str) -> dict[str, Any]:
    """Search the WordPress plugin directory and suggest a common match. Read-only."""
    from app.agent.skills.plugins import recommend_plugin

    creds = await _credentials(site_slug)
    result = await WpCli.from_credentials(creds).search_plugin(query)
    return {
        "status": "ok",
        "recommended": recommend_plugin(query),
        "results": result.stdout[:2000],
    }


@tool
async def wp_configure_plugin(
    site_slug: str, option_name: str, option_value: str, approved: bool = False
) -> dict[str, Any]:
    """Configure a plugin by setting a WordPress option via WP-CLI. WRITE — requires approved=True."""
    if not approved:
        return _needs_approval(
            "configure plugin", {"site": site_slug, "option": option_name}
        )
    creds = await _credentials(site_slug)
    result = await WpCli.from_credentials(creds).set_option(option_name, option_value)
    return {"status": "applied" if result.ok else "error", "result": result.model_dump()}


@tool
async def wp_assemble_menu(
    site_slug: str,
    menu_name: str,
    page_refs: list[int | str],
    approved: bool = False,
) -> dict[str, Any]:
    """Create a nav menu and attach the given pages to it, in order.

    ``page_refs`` are page ids (existing pages, or the ids of pages created
    earlier in the same plan). WRITE — requires approved=True.
    """
    if not approved:
        return _needs_approval(
            "assemble menu", {"site": site_slug, "menu": menu_name, "pages": page_refs}
        )
    creds = await _credentials(site_slug)
    async with WordPressRestClient.from_credentials(creds) as wp:
        menu = await wp.create_menu(menu_name)
        items: list[dict[str, Any]] = []
        for order, page_ref in enumerate(page_refs):
            page = await wp.get_page(int(page_ref))
            item = await wp.create_menu_item(
                menu.id, page_id=page.id, title=page.title, menu_order=order
            )
            items.append(item.model_dump())
    logger.info(
        "wp_assemble_menu(%s) -> menu=%s items=%d", site_slug, menu.id, len(items)
    )
    return {"status": "applied", "menu": menu.model_dump(), "items": items}


READ_TOOLS = [
    wp_list_pages,
    wp_get_page,
    wp_list_posts,
    wp_list_menus,
    wp_search_plugins,
]
WRITE_TOOLS = [
    wp_create_page,
    wp_update_page,
    wp_delete_page,
    wp_create_post,
    wp_install_plugin,
    wp_activate_plugin,
    wp_flush_elementor_css,
    wp_create_elementor_page,
    wp_publish_post,
    wp_apply_seo,
    wp_apply_theme,
    wp_configure_plugin,
    wp_assemble_menu,
]
WP_TOOLS = [*READ_TOOLS, *WRITE_TOOLS]

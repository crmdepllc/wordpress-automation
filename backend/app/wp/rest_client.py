"""Async WordPress REST API client (Application Password auth).

Covers CRUD for posts, pages, media, and menus — the read/write surface the
agent needs in Sprint 3. Content writes go through here (never WP-CLI or direct
DB), per the project's integration rules.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.wp.schemas import (
    ContentCreate,
    ContentItem,
    ContentUpdate,
    MediaItem,
    MenuItem,
    SiteCredentials,
)


class WordPressRestError(RuntimeError):
    """Raised when the WP REST API returns a non-success status."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"WP REST API error {status}: {detail}")


class WordPressRestClient:
    """Thin typed wrapper over the WP REST API for one site.

    Pass an ``httpx.AsyncClient`` to reuse a pool or to inject a mock transport
    in tests; otherwise one is created and closed with the client.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        app_password: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ):
        self._root = base_url.rstrip("/") + "/wp-json/wp/v2"
        self._auth = httpx.BasicAuth(username, app_password)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @classmethod
    def from_credentials(
        cls, creds: SiteCredentials, *, client: httpx.AsyncClient | None = None
    ) -> "WordPressRestClient":
        return cls(
            creds.base_url,
            creds.wp_username,
            creds.wp_app_password,
            client=client,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "WordPressRestClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # --- low-level ------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._client.request(
            method, f"{self._root}{path}", auth=self._auth, **kwargs
        )
        if resp.status_code >= 400:
            raise WordPressRestError(resp.status_code, resp.text[:500])
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # --- posts & pages (shared shape) -----------------------------------

    async def _list_content(self, resource: str, per_page: int) -> list[ContentItem]:
        data = await self._request("GET", f"/{resource}", params={"per_page": per_page})
        return [ContentItem.from_api(d) for d in (data or [])]

    async def _get_content(self, resource: str, item_id: int) -> ContentItem:
        return ContentItem.from_api(await self._request("GET", f"/{resource}/{item_id}"))

    async def _create_content(
        self, resource: str, payload: ContentCreate
    ) -> ContentItem:
        return ContentItem.from_api(
            await self._request("POST", f"/{resource}", json=payload.to_api())
        )

    async def _update_content(
        self, resource: str, item_id: int, payload: ContentUpdate
    ) -> ContentItem:
        return ContentItem.from_api(
            await self._request(
                "POST", f"/{resource}/{item_id}", json=payload.to_api()
            )
        )

    async def _delete_content(
        self, resource: str, item_id: int, force: bool
    ) -> None:
        await self._request(
            "DELETE", f"/{resource}/{item_id}", params={"force": str(force).lower()}
        )

    # posts
    async def list_posts(self, per_page: int = 20) -> list[ContentItem]:
        return await self._list_content("posts", per_page)

    async def get_post(self, post_id: int) -> ContentItem:
        return await self._get_content("posts", post_id)

    async def create_post(self, payload: ContentCreate) -> ContentItem:
        return await self._create_content("posts", payload)

    async def update_post(self, post_id: int, payload: ContentUpdate) -> ContentItem:
        return await self._update_content("posts", post_id, payload)

    async def delete_post(self, post_id: int, *, force: bool = False) -> None:
        await self._delete_content("posts", post_id, force)

    # pages
    async def list_pages(self, per_page: int = 20) -> list[ContentItem]:
        return await self._list_content("pages", per_page)

    async def get_page(self, page_id: int) -> ContentItem:
        return await self._get_content("pages", page_id)

    async def create_page(self, payload: ContentCreate) -> ContentItem:
        return await self._create_content("pages", payload)

    async def update_page(self, page_id: int, payload: ContentUpdate) -> ContentItem:
        return await self._update_content("pages", page_id, payload)

    async def delete_page(self, page_id: int, *, force: bool = False) -> None:
        await self._delete_content("pages", page_id, force)

    # --- Elementor page -------------------------------------------------

    async def create_elementor_page(
        self,
        title: str,
        elementor_data: list[dict[str, Any]],
        *,
        status: str = "draft",
    ) -> ContentItem:
        """Create a page whose layout is Elementor ``_elementor_data``.

        The layout is written as post meta. NOTE: ``_elementor_data`` is
        protected (underscore-prefixed) meta and is only writable over REST if
        it's registered with ``show_in_rest`` — that registration is provided by
        the project's companion WP plugin. Without it, WordPress silently drops
        the meta, so the render/integration eval is the real check here.
        """
        body = {
            "title": title,
            "status": status,
            "meta": {
                "_elementor_data": json.dumps(elementor_data),
                "_elementor_edit_mode": "builder",
                "_elementor_template_type": "wp-page",
            },
        }
        return ContentItem.from_api(await self._request("POST", "/pages", json=body))

    # --- media ----------------------------------------------------------

    async def list_media(self, per_page: int = 20) -> list[MediaItem]:
        data = await self._request("GET", "/media", params={"per_page": per_page})
        return [MediaItem.from_api(d) for d in (data or [])]

    async def upload_media(
        self, filename: str, content: bytes, mime_type: str
    ) -> MediaItem:
        data = await self._request(
            "POST",
            "/media",
            content=content,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": mime_type,
            },
        )
        return MediaItem.from_api(data)

    async def delete_media(self, media_id: int, *, force: bool = True) -> None:
        await self._request(
            "DELETE", f"/media/{media_id}", params={"force": str(force).lower()}
        )

    # --- menus ----------------------------------------------------------

    async def list_menus(self) -> list[MenuItem]:
        data = await self._request("GET", "/menus")
        return [MenuItem.from_api(d) for d in (data or [])]

    async def create_menu(self, name: str) -> MenuItem:
        return MenuItem.from_api(
            await self._request("POST", "/menus", json={"name": name})
        )

    async def delete_menu(self, menu_id: int, *, force: bool = True) -> None:
        await self._request(
            "DELETE", f"/menus/{menu_id}", params={"force": str(force).lower()}
        )

    # --- taxonomy terms (categories / tags) -----------------------------

    async def _ensure_term(self, taxonomy: str, name: str) -> int:
        """Find a term by exact name (case-insensitive) or create it; return its id."""
        found = await self._request(
            "GET", f"/{taxonomy}", params={"search": name, "per_page": 100}
        )
        for term in found or []:
            if str(term.get("name", "")).lower() == name.lower():
                return int(term["id"])
        created = await self._request("POST", f"/{taxonomy}", json={"name": name})
        return int(created["id"])

    async def ensure_category(self, name: str) -> int:
        return await self._ensure_term("categories", name)

    async def ensure_tag(self, name: str) -> int:
        return await self._ensure_term("tags", name)

    async def ensure_categories(self, names: list[str]) -> list[int]:
        return [await self.ensure_category(n) for n in names]

    async def ensure_tags(self, names: list[str]) -> list[int]:
        return [await self.ensure_tag(n) for n in names]

    # --- post/page meta (used by the SEO skill) -------------------------

    async def update_content_meta(
        self, resource: str, item_id: int, meta: dict[str, Any]
    ) -> ContentItem:
        """Set meta fields on a post/page.

        NOTE: like ``_elementor_data``, provider meta keys (e.g. Yoast's
        ``_yoast_wpseo_*``) must be registered with ``show_in_rest`` — the
        companion plugin does this — or WordPress silently ignores them.
        """
        return ContentItem.from_api(
            await self._request("POST", f"/{resource}/{item_id}", json={"meta": meta})
        )

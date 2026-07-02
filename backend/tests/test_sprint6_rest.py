"""REST additions: term find-or-create, scheduling payload, meta setter."""

from __future__ import annotations

import httpx
import respx

from app.wp.rest_client import WordPressRestClient
from app.wp.schemas import ContentCreate

BASE = "http://wp.test"
ROOT = f"{BASE}/wp-json/wp/v2"


def client() -> WordPressRestClient:
    return WordPressRestClient(BASE, "admin", "pw")


@respx.mock
async def test_ensure_category_returns_existing_id():
    respx.get(f"{ROOT}/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 5, "name": "Travel"}])
    )
    create = respx.post(f"{ROOT}/categories")
    async with client() as wp:
        assert await wp.ensure_category("Travel") == 5
    assert not create.called  # existing term → no creation


@respx.mock
async def test_ensure_tag_creates_when_missing():
    respx.get(f"{ROOT}/tags").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{ROOT}/tags").mock(
        return_value=httpx.Response(201, json={"id": 9, "name": "Hiking"})
    )
    async with client() as wp:
        assert await wp.ensure_tag("Hiking") == 9


@respx.mock
async def test_ensure_is_case_insensitive():
    respx.get(f"{ROOT}/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 3, "name": "News"}])
    )
    create = respx.post(f"{ROOT}/categories")
    async with client() as wp:
        assert await wp.ensure_category("news") == 3
    assert not create.called


def test_content_create_payload_includes_terms_and_schedule():
    payload = ContentCreate(
        title="Hi",
        content="body",
        status="future",
        categories=[1, 2],
        tags=[7],
        date="2026-12-01T09:00:00",
    ).to_api()
    assert payload["categories"] == [1, 2]
    assert payload["tags"] == [7]
    assert payload["date"] == "2026-12-01T09:00:00"
    assert payload["status"] == "future"


@respx.mock
async def test_update_content_meta_posts_meta():
    route = respx.post(f"{ROOT}/posts/12").mock(
        return_value=httpx.Response(200, json={"id": 12, "title": "T", "status": "publish"})
    )
    async with client() as wp:
        await wp.update_content_meta("posts", 12, {"_yoast_wpseo_title": "SEO"})
    assert b"_yoast_wpseo_title" in route.calls.last.request.content

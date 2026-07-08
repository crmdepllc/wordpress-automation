"""Unit tests for the WP REST client, with httpx mocked via respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.wp.rest_client import WordPressRestClient, WordPressRestError
from app.wp.schemas import ContentCreate, ContentUpdate

BASE = "http://wp.test"
ROOT = f"{BASE}/wp-json/wp/v2"


def client() -> WordPressRestClient:
    return WordPressRestClient(BASE, "admin", "app-pass")


@respx.mock
async def test_list_pages_parses_rendered_title():
    respx.get(f"{ROOT}/pages").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "title": {"rendered": "Home"}, "status": "publish",
                 "slug": "home", "link": f"{BASE}/home"}
            ],
        )
    )
    async with client() as wp:
        pages = await wp.list_pages()
    assert len(pages) == 1
    assert pages[0].id == 1
    assert pages[0].title == "Home"


@respx.mock
async def test_create_page_sends_auth_and_body():
    route = respx.post(f"{ROOT}/pages").mock(
        return_value=httpx.Response(
            201,
            json={"id": 42, "title": {"rendered": "About"}, "status": "draft",
                  "slug": "about", "link": f"{BASE}/about"},
        )
    )
    async with client() as wp:
        page = await wp.create_page(ContentCreate(title="About", content="Hi"))
    assert page.id == 42
    assert page.status == "draft"
    request = route.calls.last.request
    assert request.headers["authorization"].startswith("Basic ")
    assert b"About" in request.content


@respx.mock
async def test_update_and_delete_page():
    respx.post(f"{ROOT}/pages/42").mock(
        return_value=httpx.Response(
            200, json={"id": 42, "title": {"rendered": "About us"}, "status": "publish"}
        )
    )
    delete = respx.delete(f"{ROOT}/pages/42").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    async with client() as wp:
        updated = await wp.update_page(42, ContentUpdate(status="publish"))
        assert updated.status == "publish"
        await wp.delete_page(42, force=True)
    assert delete.calls.last.request.url.params["force"] == "true"


@respx.mock
async def test_create_and_list_posts():
    respx.post(f"{ROOT}/posts").mock(
        return_value=httpx.Response(201, json={"id": 7, "title": "News", "status": "draft"})
    )
    respx.get(f"{ROOT}/posts").mock(
        return_value=httpx.Response(200, json=[{"id": 7, "title": "News", "status": "draft"}])
    )
    async with client() as wp:
        created = await wp.create_post(ContentCreate(title="News"))
        posts = await wp.list_posts()
    assert created.id == 7
    assert posts[0].id == 7


@respx.mock
async def test_media_upload_and_list():
    upload = respx.post(f"{ROOT}/media").mock(
        return_value=httpx.Response(
            201,
            json={"id": 9, "source_url": f"{BASE}/x.png", "mime_type": "image/png",
                  "title": {"rendered": "x"}},
        )
    )
    respx.get(f"{ROOT}/media").mock(
        return_value=httpx.Response(200, json=[{"id": 9, "source_url": f"{BASE}/x.png",
                                               "mime_type": "image/png"}])
    )
    async with client() as wp:
        item = await wp.upload_media("x.png", b"\x89PNG", "image/png")
        media = await wp.list_media()
    assert item.id == 9
    assert item.mime_type == "image/png"
    assert media[0].id == 9
    assert 'filename="x.png"' in upload.calls.last.request.headers["content-disposition"]


@respx.mock
async def test_menu_create_and_list():
    respx.post(f"{ROOT}/menus").mock(
        return_value=httpx.Response(201, json={"id": 3, "name": "Main", "slug": "main"})
    )
    respx.get(f"{ROOT}/menus").mock(
        return_value=httpx.Response(200, json=[{"id": 3, "name": "Main", "slug": "main"}])
    )
    async with client() as wp:
        created = await wp.create_menu("Main")
        menus = await wp.list_menus()
    assert created.name == "Main"
    assert menus[0].id == 3


@respx.mock
async def test_create_menu_item_attaches_page():
    route = respx.post(f"{ROOT}/menu-items").mock(
        return_value=httpx.Response(
            201, json={"id": 11, "title": {"rendered": "About"}, "object_id": 42}
        )
    )
    async with client() as wp:
        item = await wp.create_menu_item(3, page_id=42, title="About", menu_order=1)
    assert item.id == 11
    assert item.object_id == 42
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "title": "About",
        "status": "publish",
        "type": "post_type",
        "object": "page",
        "object_id": 42,
        "menu_order": 1,
        "menus": 3,
    }


@respx.mock
async def test_error_status_raises():
    respx.get(f"{ROOT}/pages/999").mock(
        return_value=httpx.Response(404, text="not found")
    )
    async with client() as wp:
        with pytest.raises(WordPressRestError) as exc:
            await wp.get_page(999)
    assert exc.value.status == 404

"""Integration eval: write a generated Elementor page to the live sandbox.

Marked ``integration`` and self-skipping. Uses a fixed PageSpec (no model
needed) so it exercises the real build → validate → REST write → flush-css path
against a running WordPress+Elementor. Confirms the deliverable end-to-end when
the stack is up.

    docker compose up -d
    WP_APP_PASSWORD=... uv run pytest -m integration -k elementor

Note: persisting ``_elementor_data`` over REST needs the companion plugin to
register that meta with show_in_rest; without it WordPress drops the meta and
the page renders blank. That's exactly what this eval is here to catch.
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.agent.skills.elementor.schema import PageSpec, SectionSpec
from app.agent.skills.elementor.skill import build_and_validate
from app.wp.rest_client import WordPressRestClient

pytestmark = pytest.mark.integration

WP_URL = "http://localhost:8080"

FIXED_SPEC = PageSpec(
    title="Agent Elementor Eval",
    sections=[
        SectionSpec(type="hero", content={"heading": "Hello", "subheading": "From the agent", "cta_text": "Go"}),
        SectionSpec(type="features", items=[{"title": "A", "text": "1"}, {"title": "B", "text": "2"}, {"title": "C", "text": "3"}]),
        SectionSpec(type="contact", content={"heading": "Contact", "subheading": "Reach us", "email": "hi@x.test"}),
    ],
)


def _reachable() -> bool:
    try:
        return httpx.get(f"{WP_URL}/wp-json", timeout=3.0).status_code == 200
    except Exception:
        return False


async def test_generate_and_write_elementor_page():
    app_password = os.environ.get("WP_APP_PASSWORD")
    if not _reachable() or not app_password:
        pytest.skip("WP unreachable or WP_APP_PASSWORD not set")

    data = build_and_validate(FIXED_SPEC)  # raises if invalid

    async with WordPressRestClient(WP_URL, "admin", app_password) as wp:
        page = await wp.create_elementor_page(FIXED_SPEC.title, data, status="draft")
        assert page.id > 0
        fetched = await wp.get_page(page.id)
        assert fetched.id == page.id

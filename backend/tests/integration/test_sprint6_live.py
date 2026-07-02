"""Integration evals for the Sprint 6 skills against the live sandbox.

Marked ``integration`` and self-skipping. No LLM needed — they drive the REST /
WP-CLI write paths directly to prove content (terms + scheduling) and theming
work end-to-end when the stack is up.

    docker compose up -d
    WP_APP_PASSWORD=... uv run pytest -m integration -k sprint6
"""

from __future__ import annotations

import os
import subprocess

import httpx
import pytest

from app.agent.skills.theme.applier import apply_theme
from app.agent.skills.theme.schema import ThemeSpec
from app.config import get_settings
from app.wp.rest_client import WordPressRestClient
from app.wp.schemas import ContentCreate, SiteCredentials
from app.wp.wpcli import WpCli

pytestmark = pytest.mark.integration

WP_URL = "http://localhost:8080"


def _wp_reachable() -> bool:
    try:
        return httpx.get(f"{WP_URL}/wp-json", timeout=3.0).status_code == 200
    except Exception:
        return False


def _docker_cli_ready() -> bool:
    container = get_settings().wp_local_container
    try:
        proc = subprocess.run(
            ["docker", "exec", container, "wp", "core", "version", "--allow-root"],
            capture_output=True, timeout=20,
        )
        return proc.returncode == 0
    except Exception:
        return False


async def test_publish_post_with_category():
    app_password = os.environ.get("WP_APP_PASSWORD")
    if not _wp_reachable() or not app_password:
        pytest.skip("WP unreachable or WP_APP_PASSWORD not set")

    async with WordPressRestClient(WP_URL, "admin", app_password) as wp:
        cat_id = await wp.ensure_category("Agent News")
        assert cat_id > 0
        post = await wp.create_post(
            ContentCreate(title="Agent Post", content="<p>hi</p>", categories=[cat_id])
        )
        assert post.id > 0


async def test_apply_theme_via_wpcli_local_docker():
    if not _docker_cli_ready():
        pytest.skip("Docker WP-CLI container not available")

    creds = SiteCredentials(
        slug="sandbox", base_url=WP_URL, wp_username="admin",
        wp_app_password="unused", wpcli_transport="local_docker",
    )
    results = await apply_theme(WpCli.from_credentials(creds), ThemeSpec(footer_text="© Test"))
    # Theme-mod writes should succeed even without Elementor active.
    assert any(r["step"].startswith("color:") and r["ok"] for r in results)

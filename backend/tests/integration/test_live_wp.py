"""Integration tests against the live Dockerized WordPress instance.

Marked ``integration`` and self-skipping: if the sandbox WP isn't reachable or
Docker isn't available, these are skipped rather than failed — so the default
``pytest`` run stays green without Docker. To run them:

    docker compose up -d
    uv run pytest -m integration

Demonstrates the Sprint 3 deliverable end-to-end: a page created via the REST
tool and a plugin installed via the WP-CLI tool, both through the approved
path.
"""

from __future__ import annotations

import asyncio
import subprocess

import httpx
import pytest

from app.agent.wp_agent import run_approved
from app.config import get_settings
from app.wp.schemas import SiteCredentials
from app.wp.wpcli import LocalDockerExecutor

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
            capture_output=True,
            timeout=20,
        )
        return proc.returncode == 0
    except Exception:
        return False


def test_rest_api_reachable():
    if not _wp_reachable():
        pytest.skip("Sandbox WordPress not reachable at localhost:8080")
    resp = httpx.get(f"{WP_URL}/wp-json", timeout=5.0)
    assert resp.status_code == 200
    assert "routes" in resp.json()


async def test_install_plugin_via_wpcli_local_docker():
    if not _docker_cli_ready():
        pytest.skip("Docker WP-CLI container not available")

    creds = SiteCredentials(
        slug="sandbox",
        base_url=WP_URL,
        wp_username="admin",
        wp_app_password="unused-for-cli",
        wpcli_transport="local_docker",
    )
    executor = LocalDockerExecutor(creds)
    result = await executor.run(["plugin", "install", "hello-dolly", "--activate"])
    assert result.ok, result.stderr


async def test_create_page_via_approved_tool(monkeypatch):
    """Create a page through the gated tool path against live WP.

    Requires a real Application Password for admin; set WP_APP_PASSWORD to run,
    otherwise skipped (the sandbox's default login password won't authenticate
    REST writes).
    """
    import os

    app_password = os.environ.get("WP_APP_PASSWORD")
    if not _wp_reachable() or not app_password:
        pytest.skip("WP unreachable or WP_APP_PASSWORD not set")

    import app.agent.tools.wp_tools as wp_tools

    async def creds(site_slug):
        return SiteCredentials(
            slug=site_slug,
            base_url=WP_URL,
            wp_username="admin",
            wp_app_password=app_password,
            wpcli_transport="local_docker",
        )

    monkeypatch.setattr(wp_tools, "_credentials", creds)

    result = await run_approved(
        "wp_create_page", {"site_slug": "sandbox", "title": "Agent Test Page"}
    )
    assert result["status"] == "applied"
    assert result["page"]["id"] > 0

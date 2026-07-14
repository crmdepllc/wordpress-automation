"""Unit tests for the WP-CLI executors and high-level WpCli."""

from __future__ import annotations

import asyncio

import pytest

from app.wp.schemas import CliResult, SiteCredentials
from app.wp.wpcli import (
    LocalDockerExecutor,
    SshExecutor,
    WpCli,
    build_executor,
)


class RecordingExecutor:
    """Captures the args passed to run(); returns a canned success."""

    def __init__(self):
        self.calls: list[list[str]] = []

    async def run(self, args: list[str]) -> CliResult:
        self.calls.append(args)
        return CliResult(command=" ".join(args), exit_code=0, stdout="ok")


def local_creds() -> SiteCredentials:
    return SiteCredentials(
        slug="local",
        base_url="http://localhost:8080",
        wp_username="admin",
        wp_app_password="pw",
        wpcli_transport="local_docker",
    )


def ssh_creds() -> SiteCredentials:
    return SiteCredentials(
        slug="remote",
        base_url="https://client.example",
        wp_username="admin",
        wp_app_password="pw",
        wpcli_transport="ssh",
        ssh_host="1.2.3.4",
        ssh_user="deploy",
    )


def test_build_executor_picks_transport():
    assert isinstance(build_executor(local_creds()), LocalDockerExecutor)
    assert isinstance(build_executor(ssh_creds()), SshExecutor)


async def test_wpcli_builds_install_args():
    rec = RecordingExecutor()
    cli = WpCli(rec)
    await cli.install_plugin("elementor", activate=True)
    await cli.activate_plugin("akismet")
    await cli.flush_css()
    assert rec.calls[0] == ["plugin", "install", "elementor", "--activate"]
    assert rec.calls[1] == ["plugin", "activate", "akismet"]
    assert rec.calls[2] == ["elementor", "flush-css"]


async def test_wpcli_builds_plugin_status_args():
    rec = RecordingExecutor()
    cli = WpCli(rec)
    await cli.plugin_is_installed("elementor")
    await cli.plugin_is_active("elementor")
    assert rec.calls[0] == ["plugin", "is-installed", "elementor"]
    assert rec.calls[1] == ["plugin", "is-active", "elementor"]


async def test_wpcli_builds_theme_args():
    rec = RecordingExecutor()
    cli = WpCli(rec)
    await cli.theme_is_installed("astra")
    await cli.theme_is_active("astra")
    await cli.install_theme("astra", activate=True)
    await cli.activate_theme("astra")
    assert rec.calls[0] == ["theme", "is-installed", "astra"]
    assert rec.calls[1] == ["theme", "is-active", "astra"]
    assert rec.calls[2] == ["theme", "install", "astra", "--activate"]
    assert rec.calls[3] == ["theme", "activate", "astra"]


async def test_wpcli_install_theme_without_activate():
    rec = RecordingExecutor()
    await WpCli(rec).install_theme("astra", activate=False)
    assert rec.calls[0] == ["theme", "install", "astra"]


async def test_wpcli_export_db_builds_args():
    rec = RecordingExecutor()
    result = await WpCli(rec).export_db("snapshot-acme-20260709.sql")
    assert rec.calls[0] == ["db", "export", "snapshot-acme-20260709.sql"]
    assert result.ok


async def test_update_post_meta_plain_vs_json():
    rec = RecordingExecutor()
    cli = WpCli(rec)
    await cli.update_post_meta(4, "some_key", "plain value")
    await cli.update_post_meta(4, "_elementor_page_settings", '{"a": 1}', as_json=True)
    assert rec.calls[0] == ["post", "meta", "update", "4", "some_key", "plain value"]
    # --format=json tells WP-CLI to decode+store a real PHP array, not a string
    # — required for Elementor's Controls_Stack, which fatals on a plain string.
    assert rec.calls[1] == [
        "post", "meta", "update", "4", "_elementor_page_settings", '{"a": 1}', "--format=json",
    ]


async def test_local_docker_executor_command(monkeypatch):
    captured: dict[str, object] = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"Success", b""

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    ex = LocalDockerExecutor(local_creds(), container="wpcli-test")
    result = await ex.run(["plugin", "install", "elementor", "--activate"])

    assert result.ok
    assert result.stdout == "Success"
    args = captured["args"]
    assert args[:3] == ("docker", "exec", "wpcli-test")
    assert "wp" in args
    assert args[-1] == "--allow-root"


async def test_ssh_executor_runs_command(monkeypatch):
    captured: dict[str, str] = {}

    class FakeResult:
        exited = 0
        stdout = "done"
        stderr = ""

    class FakeConnection:
        def __init__(self, **kwargs):
            captured["host"] = kwargs.get("host", "")

        def run(self, command, **kwargs):
            captured["command"] = command
            return FakeResult()

    monkeypatch.setattr("fabric.Connection", FakeConnection)

    ex = SshExecutor(ssh_creds())
    result = await ex.run(["plugin", "install", "elementor"])

    assert result.exit_code == 0
    assert captured["host"] == "1.2.3.4"
    assert captured["command"] == "wp plugin install elementor"


def test_ssh_executor_requires_host():
    bad = ssh_creds().model_copy(update={"ssh_host": None})
    with pytest.raises(ValueError):
        SshExecutor(bad)

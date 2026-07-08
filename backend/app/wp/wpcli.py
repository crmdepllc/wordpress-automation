"""WP-CLI execution with a pluggable transport.

Per the integration rules, plugin installs/activation and Elementor CSS flush
go through WP-CLI (never the REST API or direct DB). Two transports share one
interface:

  - ``SshExecutor``        — real remote client sites, via Fabric/Paramiko.
  - ``LocalDockerExecutor`` — the local Docker sandbox, via ``docker exec``.

The transport is chosen per-site from ``SiteCredentials.wpcli_transport``.
"""

from __future__ import annotations

import asyncio
import io
import subprocess
from typing import Protocol

from app.config import get_settings
from app.wp.schemas import CliResult, SiteCredentials


class WpCliExecutor(Protocol):
    """Runs a WP-CLI argument list and returns its result."""

    async def run(self, args: list[str]) -> CliResult: ...


class SshExecutor:
    """Runs WP-CLI on a remote host over SSH using Fabric/Paramiko."""

    def __init__(self, creds: SiteCredentials):
        if not creds.ssh_host or not creds.ssh_user:
            raise ValueError("SSH transport requires ssh_host and ssh_user.")
        self._creds = creds

    def _run_sync(self, command: str) -> CliResult:
        # Imported lazily so unit tests that mock this never need Fabric.
        from fabric import Connection  # type: ignore[import-untyped]

        connect_kwargs: dict[str, object] = {}
        if self._creds.ssh_private_key:
            import paramiko

            pkey = paramiko.RSAKey.from_private_key(
                io.StringIO(self._creds.ssh_private_key)
            )
            connect_kwargs["pkey"] = pkey

        conn = Connection(
            host=self._creds.ssh_host,
            user=self._creds.ssh_user,
            port=self._creds.ssh_port,
            connect_kwargs=connect_kwargs,
        )
        result = conn.run(command, hide=True, warn=True)
        return CliResult(
            command=command,
            exit_code=result.exited,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    async def run(self, args: list[str]) -> CliResult:
        command = " ".join([self._creds.wp_cli_path, *args])
        return await asyncio.to_thread(self._run_sync, command)


class LocalDockerExecutor:
    """Runs WP-CLI in the local sandbox via ``docker exec`` into the cli container."""

    def __init__(self, creds: SiteCredentials, container: str | None = None):
        self._creds = creds
        self._container = container or get_settings().wp_local_container

    def _run_sync(self, full: list[str]) -> CliResult:
        result = subprocess.run(full, capture_output=True, text=True)
        return CliResult(
            command=" ".join(full),
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    async def run(self, args: list[str]) -> CliResult:
        # --allow-root because the sandbox cli container runs as root.
        full = [
            "docker",
            "exec",
            self._container,
            self._creds.wp_cli_path,
            *args,
            "--allow-root",
        ]
        # Plain subprocess.run in a thread, not asyncio.create_subprocess_exec:
        # on Windows, subprocess creation needs the Proactor event loop, but
        # uvicorn's --reload workers (spawned via multiprocessing) start on a
        # fresh Selector loop that raises a bare NotImplementedError. Matches
        # SshExecutor's existing to_thread pattern above.
        return await asyncio.to_thread(self._run_sync, full)


def build_executor(creds: SiteCredentials) -> WpCliExecutor:
    """Pick the transport for a site from its credentials."""
    if creds.wpcli_transport == "local_docker":
        return LocalDockerExecutor(creds)
    return SshExecutor(creds)


class WpCli:
    """High-level WP-CLI operations the agent needs in Sprint 3."""

    def __init__(self, executor: WpCliExecutor):
        self._executor = executor

    @classmethod
    def from_credentials(cls, creds: SiteCredentials) -> "WpCli":
        return cls(build_executor(creds))

    async def install_plugin(self, slug: str, *, activate: bool = True) -> CliResult:
        args = ["plugin", "install", slug]
        if activate:
            args.append("--activate")
        return await self._executor.run(args)

    async def activate_plugin(self, slug: str) -> CliResult:
        return await self._executor.run(["plugin", "activate", slug])

    async def flush_css(self) -> CliResult:
        """Regenerate Elementor CSS — run after every layout write."""
        return await self._executor.run(["elementor", "flush-css"])

    async def search_plugin(self, query: str, *, limit: int = 10) -> CliResult:
        """Search the plugin directory. Read-only."""
        return await self._executor.run(
            [
                "plugin",
                "search",
                query,
                "--format=json",
                "--fields=name,slug,rating",
                f"--per-page={limit}",
            ]
        )

    async def set_option(self, name: str, value: str) -> CliResult:
        """Set a WordPress option (used to configure plugins)."""
        return await self._executor.run(["option", "update", name, value])

    async def set_theme_mod(self, name: str, value: str) -> CliResult:
        """Set a theme modification (Customizer setting) for the active theme."""
        return await self._executor.run(["theme", "mod", "set", name, value])

    async def get_option(self, name: str) -> CliResult:
        """Read a WordPress option (e.g. the active Elementor kit id)."""
        return await self._executor.run(["option", "get", name])

    async def update_post_meta(self, post_id: int, key: str, value: str) -> CliResult:
        """Set a single post-meta value (used for Elementor kit settings)."""
        return await self._executor.run(
            ["post", "meta", "update", str(post_id), key, value]
        )

    async def get_post_meta(self, post_id: int, key: str) -> CliResult:
        """Read a single post-meta value as JSON."""
        return await self._executor.run(
            ["post", "meta", "get", str(post_id), key, "--format=json"]
        )

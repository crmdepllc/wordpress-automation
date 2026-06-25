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
        proc = await asyncio.create_subprocess_exec(
            *full,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return CliResult(
            command=" ".join(full),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=out.decode(errors="replace"),
            stderr=err.decode(errors="replace"),
        )


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

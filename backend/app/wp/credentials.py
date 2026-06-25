"""Per-site credential storage.

Stores and retrieves WordPress site credentials. Secret fields are encrypted at
rest by the ``EncryptedString`` column type, so this service deals in plaintext
``SiteCredentials`` while the database only ever sees ciphertext.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WpCliTransport, WpSite
from app.wp.schemas import SiteCredentials


class SiteNotFoundError(LookupError):
    """Raised when no site exists for the given slug."""


def _to_credentials(site: WpSite) -> SiteCredentials:
    return SiteCredentials(
        slug=site.slug,
        base_url=site.base_url,
        wp_username=site.wp_username,
        wp_app_password=site.wp_app_password,
        wpcli_transport=site.wpcli_transport.value,
        ssh_host=site.ssh_host,
        ssh_port=site.ssh_port,
        ssh_user=site.ssh_user,
        ssh_private_key=site.ssh_private_key,
        wp_cli_path=site.wp_cli_path,
    )


async def get_site_credentials(session: AsyncSession, slug: str) -> SiteCredentials:
    site = await session.scalar(select(WpSite).where(WpSite.slug == slug))
    if site is None:
        raise SiteNotFoundError(f"No WordPress site registered with slug '{slug}'.")
    return _to_credentials(site)


async def list_site_slugs(session: AsyncSession) -> list[str]:
    rows = await session.scalars(select(WpSite.slug).order_by(WpSite.slug))
    return list(rows)


async def upsert_site(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    base_url: str,
    wp_username: str,
    wp_app_password: str,
    wpcli_transport: str = "ssh",
    ssh_host: str | None = None,
    ssh_port: int = 22,
    ssh_user: str | None = None,
    ssh_private_key: str | None = None,
    wp_cli_path: str = "wp",
) -> WpSite:
    """Create a site or update it in place if the slug already exists."""
    site = await session.scalar(select(WpSite).where(WpSite.slug == slug))
    if site is None:
        site = WpSite(slug=slug)
        session.add(site)

    site.name = name
    site.base_url = base_url
    site.wp_username = wp_username
    site.wp_app_password = wp_app_password
    site.wpcli_transport = WpCliTransport(wpcli_transport)
    site.ssh_host = ssh_host
    site.ssh_port = ssh_port
    site.ssh_user = ssh_user
    site.ssh_private_key = ssh_private_key
    site.wp_cli_path = wp_cli_path

    await session.commit()
    await session.refresh(site)
    return site

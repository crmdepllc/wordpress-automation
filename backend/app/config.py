"""Typed application configuration.

All configuration is read from environment variables (and, for local dev, a
``.env`` file). Secrets — the Anthropic API key, database URLs, SSH targets —
live here and are NEVER hardcoded. See ``.env.example`` for the full list.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Anthropic / Claude ------------------------------------------------
    # Required for the agent to talk to Claude. Left empty by default so the
    # app can still boot (e.g. for /health) without a key; the ping route
    # raises a clear error if it is missing.
    anthropic_api_key: str = ""

    # Per AGENTS.md model-routing rule: orchestrator reasoning uses the larger
    # model; fast, narrow sub-tasks (like the ping spike) use the smaller one.
    orchestrator_model: str = "claude-opus-4-8"
    fast_model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1024

    # --- Data services (used by later sprints; defined now for compose) ----
    database_url: str = "postgresql+asyncpg://wpa:wpa@postgres:5432/wpa"
    redis_url: str = "redis://redis:6379/0"

    # --- Credential encryption --------------------------------------------
    # Fernet key used to encrypt WordPress site credentials at rest in
    # Postgres. NEVER hardcoded. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Empty by default so the app boots without it; the credentials service
    # raises a clear error if a credential operation runs without a key set.
    credential_encryption_key: str = ""

    # --- Local sandbox WP-CLI (docker exec transport) ---------------------
    # Name of the persistent WP-CLI container that the LocalDockerExecutor
    # shells into for WP-CLI in dev/tests (the `wpcli` compose service). Real
    # client sites use SSH instead.
    wp_local_container: str = "wordpress-automation-wpcli-1"

    # --- HTTP / CORS -------------------------------------------------------
    # Comma-separated list of allowed origins for the browser dashboard.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

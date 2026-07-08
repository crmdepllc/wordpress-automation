"""add local_process wpcli transport + cli_cwd/cli_env columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09

Adds a third WP-CLI transport for locally-installed dev sites (e.g. Local by
WP Engine) that are neither a remote SSH host nor the project's Docker
sandbox: WP-CLI runs as a plain local subprocess with a site-specific working
directory and environment (bundled PHP's PHPRC, PATH additions, etc).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE wpcli_transport ADD VALUE IF NOT EXISTS 'local_process'")
    op.add_column("wp_sites", sa.Column("cli_cwd", sa.String(length=1024), nullable=True))
    op.add_column("wp_sites", sa.Column("cli_env", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("wp_sites", "cli_env")
    op.drop_column("wp_sites", "cli_cwd")
    # Postgres cannot drop a single enum value; downgrading the enum itself
    # would require recreating the type. Left as-is (additive, harmless).

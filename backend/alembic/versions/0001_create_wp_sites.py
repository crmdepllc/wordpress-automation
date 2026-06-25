"""create wp_sites

Revision ID: 0001
Revises:
Create Date: 2026-06-25

Initial schema: the per-site WordPress credential store. Secret columns are
stored as Text (Fernet-encrypted by the app's EncryptedString type).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    wpcli_transport = sa.Enum("ssh", "local_docker", name="wpcli_transport")
    op.create_table(
        "wp_sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("wp_username", sa.String(length=255), nullable=False),
        # Encrypted at rest (Fernet token), so stored as Text.
        sa.Column("wp_app_password", sa.Text(), nullable=False),
        sa.Column(
            "wpcli_transport",
            wpcli_transport,
            nullable=False,
            server_default="ssh",
        ),
        sa.Column("ssh_host", sa.Text(), nullable=True),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_user", sa.Text(), nullable=True),
        sa.Column("ssh_private_key", sa.Text(), nullable=True),
        sa.Column(
            "wp_cli_path", sa.String(length=255), nullable=False, server_default="wp"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_wp_sites_slug", "wp_sites", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_wp_sites_slug", table_name="wp_sites")
    op.drop_table("wp_sites")
    sa.Enum(name="wpcli_transport").drop(op.get_bind(), checkfirst=True)

"""create tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25

Orchestration task metadata so a paused task can be listed and resumed after a
restart. The graph's own state lives in the LangGraph Postgres checkpoint
tables (created by AsyncPostgresSaver.setup()); this table just maps a task id
to its site/instruction/status.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("site_slug", sa.String(length=64), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planning"),
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
    op.create_index("ix_tasks_site_slug", "tasks", ["site_slug"])


def downgrade() -> None:
    op.drop_index("ix_tasks_site_slug", table_name="tasks")
    op.drop_table("tasks")

"""add conversation support to user_inputs

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_inputs",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_inputs_conversation_id", "user_inputs", ["conversation_id"]
    )
    op.add_column(
        "user_inputs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_inputs", "updated_at")
    op.drop_index("ix_user_inputs_conversation_id", table_name="user_inputs")
    op.drop_column("user_inputs", "conversation_id")

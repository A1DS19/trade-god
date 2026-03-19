"""Add trades table and partial_taken to positions

Revision ID: 001
Revises:
Create Date: 2026-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column(
            "partial_taken",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("coin", sa.String(20), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("avg_buy", sa.Float(), nullable=True),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(30), nullable=True),
        sa.Column("timestamp", sa.String(30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_column("positions", "partial_taken")

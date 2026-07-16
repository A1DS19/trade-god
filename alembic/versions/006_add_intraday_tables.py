"""add intraday paper-engine tables

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intraday_trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(5), nullable=False, server_default="long"),
        sa.Column("mode", sa.String(5), nullable=False),
        sa.Column("limit_price", sa.Float, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("slot_usd", sa.Float, nullable=False),
        sa.Column("entry_time", sa.String(50), nullable=False),
        sa.Column("exit_time", sa.String(50), nullable=True),
        sa.Column("hold_bars", sa.Integer, nullable=True),
        sa.Column("pnl_pct", sa.Float, nullable=True),
        sa.Column("pnl_usd", sa.Float, nullable=True),
        sa.Column("fill_type", sa.String(15), nullable=False),
        sa.Column("exit_reason", sa.String(30), nullable=True),
        sa.Column("status", sa.String(6), nullable=False, server_default="open"),
    )
    op.create_table(
        "intraday_limits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("limit_price", sa.Float, nullable=False),
        sa.Column("placed_at", sa.String(50), nullable=False),
        sa.Column("resolved_at", sa.String(50), nullable=True),
        sa.Column("outcome", sa.String(15), nullable=True),
        sa.Column("bar_low", sa.Float, nullable=True),
        sa.Column("admitted", sa.Boolean, nullable=True),
    )
    op.create_table(
        "intraday_state",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated", sa.String(50), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("intraday_state")
    op.drop_table("intraday_limits")
    op.drop_table("intraday_trades")

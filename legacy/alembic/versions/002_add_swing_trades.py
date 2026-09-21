"""Add swing_trades table

Revision ID: 002
Revises: 001
Create Date: 2026-03-20

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "swing_trades",
        sa.Column("id",               sa.Integer(),    autoincrement=True, nullable=False),
        sa.Column("coin",             sa.String(20),   nullable=False),
        sa.Column("direction",        sa.String(5),    nullable=False),
        sa.Column("entry_price",      sa.Float(),      nullable=False),
        sa.Column("exit_price",       sa.Float(),      nullable=True),
        sa.Column("qty",              sa.Float(),      nullable=False),
        sa.Column("leverage",         sa.Integer(),    nullable=False),
        sa.Column("notional_usdt",    sa.Float(),      nullable=False),
        sa.Column("entry_time",       sa.String(30),   nullable=False),
        sa.Column("exit_time",        sa.String(30),   nullable=True),
        sa.Column("realized_pnl_usd", sa.Float(),      nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(),      nullable=True),
        sa.Column("exit_reason",      sa.String(50),   nullable=True),
        sa.Column("agent_confidence", sa.Float(),      nullable=False),
        sa.Column("agent_reasoning",  sa.String(500),  nullable=True),
        sa.Column("status",           sa.String(6),    nullable=False, server_default="open"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("swing_trades")

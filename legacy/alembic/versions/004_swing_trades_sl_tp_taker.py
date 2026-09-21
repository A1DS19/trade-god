"""Add entry_sl_pct, entry_tp_pct to swing_trades; widen exit_reason to 100

Revision ID: 004
Revises: 003
Create Date: 2026-03-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("swing_trades", sa.Column("entry_sl_pct", sa.Float(), nullable=True))
    op.add_column("swing_trades", sa.Column("entry_tp_pct", sa.Float(), nullable=True))
    op.alter_column("swing_trades", "exit_reason",
                    existing_type=sa.String(50),
                    type_=sa.String(100),
                    existing_nullable=True)


def downgrade() -> None:
    op.drop_column("swing_trades", "entry_sl_pct")
    op.drop_column("swing_trades", "entry_tp_pct")
    op.alter_column("swing_trades", "exit_reason",
                    existing_type=sa.String(100),
                    type_=sa.String(50),
                    existing_nullable=True)

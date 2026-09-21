"""Widen swing_trades entry_time and exit_time to VARCHAR(50)

Revision ID: 003
Revises: 002
Create Date: 2026-03-20

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("swing_trades", "entry_time", type_=sa.String(50), existing_nullable=False)
    op.alter_column("swing_trades", "exit_time",  type_=sa.String(50), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("swing_trades", "entry_time", type_=sa.String(30), existing_nullable=False)
    op.alter_column("swing_trades", "exit_time",  type_=sa.String(30), existing_nullable=True)

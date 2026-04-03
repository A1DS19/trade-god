"""Normalize swing_trades entry_sl_pct/entry_tp_pct from percent units to fractions

Revision ID: 005
Revises: 004
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Historical bug stored values like 3.176 for 3.176%.
    # Normalize to fractions (0.03176) expected by runtime logic.
    op.execute(sa.text(
        "UPDATE swing_trades SET entry_sl_pct = entry_sl_pct / 100.0 "
        "WHERE entry_sl_pct IS NOT NULL AND entry_sl_pct > 1"
    ))
    op.execute(sa.text(
        "UPDATE swing_trades SET entry_tp_pct = entry_tp_pct / 100.0 "
        "WHERE entry_tp_pct IS NOT NULL AND entry_tp_pct > 1"
    ))


def downgrade() -> None:
    # No-op: values are now in canonical units.
    pass

"""Expand allocation result storage

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("allocation_runs", "result_json", existing_type=sa.String(length=20000), type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("allocation_runs", "result_json", existing_type=sa.Text(), type_=sa.String(length=20000), existing_nullable=False)

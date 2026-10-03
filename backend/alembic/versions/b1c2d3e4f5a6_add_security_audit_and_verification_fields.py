"""Add security audit and phone verification fields

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-10-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("requires_phone_verification", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("is_phone_verified", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("allocation_runs", sa.Column("revealed_seed", sa.String(length=128), nullable=True))
    op.add_column("allocation_runs", sa.Column("allocation_result_hash", sa.String(length=128), nullable=True))
    op.add_column("allocation_runs", sa.Column("commitment_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("allocation_runs", sa.Column("allocation_executed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("allocation_runs", "allocation_executed_at")
    op.drop_column("allocation_runs", "commitment_created_at")
    op.drop_column("allocation_runs", "allocation_result_hash")
    op.drop_column("allocation_runs", "revealed_seed")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "is_phone_verified")
    op.drop_column("events", "requires_phone_verification")

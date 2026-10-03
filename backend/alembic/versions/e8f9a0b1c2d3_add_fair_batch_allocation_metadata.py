"""Add fair batch allocation metadata

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("registration_start", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True))
    op.add_column("events", sa.Column("batch_duration_seconds", sa.Integer(), server_default="120", nullable=False))
    op.add_column("events", sa.Column("batch_weights", sa.JSON(), nullable=True))
    op.add_column("entries", sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True))
    op.add_column("entries", sa.Column("batch_id", sa.String(length=80), nullable=True))
    op.add_column("entries", sa.Column("randomized_position", sa.Integer(), nullable=True))
    op.add_column("entries", sa.Column("allocation_status", sa.String(length=50), nullable=True))
    op.add_column("entries", sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE entries SET joined_at = created_at WHERE joined_at IS NULL")
    op.alter_column("entries", "joined_at", nullable=False)
    op.create_table(
        "allocation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_seed", sa.String(length=128), nullable=False),
        sa.Column("seed_commitment", sa.String(length=128), nullable=False),
        sa.Column("batch_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("allocation_policy", sa.JSON(), nullable=False),
        sa.Column("batch_definitions", sa.JSON(), nullable=False),
        sa.Column("entry_list_hash", sa.String(length=128), nullable=False),
        sa.Column("eligible_entry_count", sa.Integer(), nullable=False),
        sa.Column("winner_count", sa.Integer(), nullable=False),
        sa.Column("waitlist_count", sa.Integer(), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.add_column("allocations", sa.Column("allocation_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_allocations_allocation_run", "allocations", "allocation_runs", ["allocation_run_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_allocations_allocation_run", "allocations", type_="foreignkey")
    op.drop_column("allocations", "allocation_run_id")
    op.drop_table("allocation_runs")
    op.drop_column("entries", "allocated_at")
    op.drop_column("entries", "allocation_status")
    op.drop_column("entries", "randomized_position")
    op.drop_column("entries", "batch_id")
    op.drop_column("entries", "joined_at")
    op.drop_column("events", "batch_weights")
    op.drop_column("events", "batch_duration_seconds")
    op.drop_column("events", "registration_start")

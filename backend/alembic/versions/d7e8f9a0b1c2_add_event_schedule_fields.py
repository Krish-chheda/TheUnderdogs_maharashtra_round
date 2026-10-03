"""Add venue and schedule fields to events

Revision ID: d7e8f9a0b1c2
Revises: c2f4b8a9d1e2
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c2f4b8a9d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("venue", sa.String(length=255), nullable=True))
    op.add_column("events", sa.Column("event_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "registration_deadline")
    op.drop_column("events", "event_date")
    op.drop_column("events", "venue")

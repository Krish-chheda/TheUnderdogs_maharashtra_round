"""Add email password and roles to users

Revision ID: c2f4b8a9d1e2
Revises: af1bf7605fb3
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f4b8a9d1e2"
down_revision: Union[str, Sequence[str], None] = "af1bf7605fb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=20), server_default="user", nullable=True))
    op.execute("UPDATE users SET email = phone || '@otp.local', password_hash = '' WHERE email IS NULL")
    op.alter_column("users", "email", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)
    op.alter_column("users", "role", nullable=False)
    op.alter_column("users", "phone", nullable=True)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")

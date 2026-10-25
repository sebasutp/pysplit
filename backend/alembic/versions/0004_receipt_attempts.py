"""Bound paid receipt extraction retries with an attempt counter.

Revision ID: 0004_receipt_attempts
Revises: 0003_sync_and_auth_schema
Create Date: 2026-10-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_receipt_attempts"
down_revision = "0003_sync_and_auth_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    # The server default only exists so existing rows can be backfilled; the
    # model supplies the value on insert. Dropping it keeps the migrated schema
    # identical to ``SQLModel.metadata.create_all``.
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.alter_column("attempts", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.drop_column("attempts")

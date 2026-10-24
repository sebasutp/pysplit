"""Receipts schema: receipts, items, portions and opt-outs.

Revision ID: 0002_receipts_schema
Revises: 0001_core_schema
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.types import UTCDateTime

revision = "0002_receipts_schema"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_extraction", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("merchant", sa.String(), nullable=True),
        sa.Column("receipt_date", UTCDateTime(), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("expense_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "group_id", "image_url", name="uq_receipts_group_image"
        ),
        sa.UniqueConstraint("expense_id"),
    )
    op.create_index("ix_receipts_group_id", "receipts", ["group_id"])
    op.create_index("ix_receipts_updated_at", "receipts", ["updated_at"])

    op.create_table(
        "receipt_items",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity_milli", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("is_adjustment", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["receipt_id"], ["receipts.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_receipt_items_receipt_id", "receipt_items", ["receipt_id"])
    op.create_index("ix_receipt_items_updated_at", "receipt_items", ["updated_at"])
    op.create_index(
        "ix_receipt_items_receipt_position",
        "receipt_items",
        ["receipt_id", "position"],
    )

    op.create_table(
        "receipt_item_portions",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("participant_id", sa.String(length=64), nullable=True),
        sa.Column("quantity_milli", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["receipt_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_receipt_item_portions_item_id", "receipt_item_portions", ["item_id"]
    )
    op.create_index(
        "ix_receipt_item_portions_participant_id",
        "receipt_item_portions",
        ["participant_id"],
    )
    op.create_index(
        "ix_receipt_item_portions_updated_at",
        "receipt_item_portions",
        ["updated_at"],
    )

    op.create_table(
        "receipt_opt_outs",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("participant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["receipt_id"], ["receipts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "participant_id",
            name="uq_receipt_opt_outs_receipt_participant",
        ),
    )
    op.create_index(
        "ix_receipt_opt_outs_receipt_id", "receipt_opt_outs", ["receipt_id"]
    )
    op.create_index(
        "ix_receipt_opt_outs_participant_id", "receipt_opt_outs", ["participant_id"]
    )
    op.create_index(
        "ix_receipt_opt_outs_updated_at", "receipt_opt_outs", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_table("receipt_opt_outs")
    op.drop_table("receipt_item_portions")
    op.drop_table("receipt_items")
    op.drop_table("receipts")

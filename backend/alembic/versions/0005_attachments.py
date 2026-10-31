"""Unify expense documents and receipts into attachments.

This is intentionally destructive: the application has not shipped to
production, so there is no data to preserve.

Revision ID: 0005_attachments
Revises: 0004_receipt_attempts
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.types import UTCDateTime

revision = "0005_attachments"
down_revision = "0004_receipt_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("receipt_opt_outs")
    op.drop_table("receipt_item_portions")
    op.drop_table("receipt_items")
    op.drop_table("receipts")
    op.drop_table("expense_documents")

    op.create_table(
        "attachments",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("expense_id", sa.String(length=64), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("receipt_status", sa.String(length=32), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("raw_extraction", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("merchant", sa.String(), nullable=True),
        sa.Column("receipt_date", UTCDateTime(), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_attachments_group_id", "attachments", ["group_id"])
    op.create_index("ix_attachments_expense_id", "attachments", ["expense_id"])
    op.create_index("ix_attachments_updated_at", "attachments", ["updated_at"])
    op.create_index(
        "ix_attachments_group_expense", "attachments", ["group_id", "expense_id"]
    )
    op.create_index(
        "ix_attachments_expense_status",
        "attachments",
        ["expense_id", "receipt_status"],
    )

    op.create_table(
        "attachment_items",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("attachment_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity_milli", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("is_adjustment", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_attachment_items_attachment_id", "attachment_items", ["attachment_id"]
    )
    op.create_index("ix_attachment_items_updated_at", "attachment_items", ["updated_at"])
    op.create_index(
        "ix_attachment_items_attachment_position",
        "attachment_items",
        ["attachment_id", "position"],
    )

    op.create_table(
        "attachment_item_portions",
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
            ["item_id"], ["attachment_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_attachment_item_portions_item_id",
        "attachment_item_portions",
        ["item_id"],
    )
    op.create_index(
        "ix_attachment_item_portions_participant_id",
        "attachment_item_portions",
        ["participant_id"],
    )
    op.create_index(
        "ix_attachment_item_portions_updated_at",
        "attachment_item_portions",
        ["updated_at"],
    )

    op.create_table(
        "attachment_opt_outs",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("attachment_id", sa.String(length=64), nullable=False),
        sa.Column("participant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "attachment_id",
            "participant_id",
            name="uq_attachment_opt_outs_attachment_participant",
        ),
    )
    op.create_index(
        "ix_attachment_opt_outs_attachment_id",
        "attachment_opt_outs",
        ["attachment_id"],
    )
    op.create_index(
        "ix_attachment_opt_outs_participant_id",
        "attachment_opt_outs",
        ["participant_id"],
    )
    op.create_index(
        "ix_attachment_opt_outs_updated_at",
        "attachment_opt_outs",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_table("attachment_opt_outs")
    op.drop_table("attachment_item_portions")
    op.drop_table("attachment_items")
    op.drop_table("attachments")

    # Re-create the pre-0005 tables so the older migrations can drop them while
    # walking down to base. Data is intentionally not restored.
    op.create_table(
        "expense_documents",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("expense_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
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
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
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
    )

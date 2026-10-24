"""Core schema: groups, participants, expenses, activities, recurrence.

Revision ID: 0001_core_schema
Revises:
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.types import DecimalString, UTCDateTime

revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("information", sa.String(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_groups_updated_at", "groups", ["updated_at"])

    op.create_table(
        "participants",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_participants_group_id", "participants", ["group_id"])
    op.create_index("ix_participants_updated_at", "participants", ["updated_at"])

    op.create_table(
        "categories",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grouping", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_index("ix_categories_updated_at", "categories", ["updated_at"])

    op.create_table(
        "expenses",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("expense_date", UTCDateTime(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("original_amount", sa.Integer(), nullable=True),
        sa.Column("original_currency", sa.String(length=8), nullable=True),
        sa.Column("conversion_rate", DecimalString(), nullable=True),
        sa.Column("paid_by_id", sa.String(), nullable=False),
        sa.Column("is_reimbursement", sa.Boolean(), nullable=False),
        sa.Column("split_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("recurrence_rule", sa.String(length=32), nullable=True),
        sa.Column("recurring_expense_link_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["paid_by_id"], ["participants.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_expenses_group_id", "expenses", ["group_id"])
    op.create_index("ix_expenses_category_id", "expenses", ["category_id"])
    op.create_index("ix_expenses_paid_by", "expenses", ["paid_by_id"])
    op.create_index(
        "ix_expenses_recurring_expense_link_id",
        "expenses",
        ["recurring_expense_link_id"],
    )
    op.create_index("ix_expenses_updated_at", "expenses", ["updated_at"])
    op.create_index(
        "ix_expenses_group_expense_date", "expenses", ["group_id", "expense_date"]
    )
    op.create_index(
        "ix_expenses_group_created_at", "expenses", ["group_id", "created_at"]
    )

    op.create_table(
        "expense_paid_for",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("expense_id", sa.String(length=64), primary_key=True),
        sa.Column("participant_id", sa.String(length=64), primary_key=True),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_expense_paid_for_participant_id",
        "expense_paid_for",
        ["participant_id"],
    )
    op.create_index(
        "ix_expense_paid_for_updated_at", "expense_paid_for", ["updated_at"]
    )

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
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expenses.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_expense_documents_expense_id", "expense_documents", ["expense_id"]
    )
    op.create_index(
        "ix_expense_documents_updated_at", "expense_documents", ["updated_at"]
    )

    op.create_table(
        "activities",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("time", UTCDateTime(), nullable=False),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("participant_id", sa.String(length=64), nullable=True),
        sa.Column("expense_id", sa.String(length=64), nullable=True),
        sa.Column("data", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_activities_group_id", "activities", ["group_id"])
    op.create_index("ix_activities_updated_at", "activities", ["updated_at"])
    op.create_index(
        "ix_activities_group_time", "activities", ["group_id", "time"]
    )

    op.create_table(
        "recurring_expense_links",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("current_frame_expense_id", sa.String(length=64), nullable=False),
        sa.Column("next_expense_created_at", UTCDateTime(), nullable=True),
        sa.Column("next_expense_date", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["current_frame_expense_id"],
            ["expenses.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("current_frame_expense_id"),
    )
    op.create_index(
        "ix_recurring_expense_links_group_id",
        "recurring_expense_links",
        ["group_id"],
    )
    op.create_index(
        "ix_recurring_expense_links_updated_at",
        "recurring_expense_links",
        ["updated_at"],
    )
    op.create_index(
        "ix_recurring_links_group_next",
        "recurring_expense_links",
        ["group_id", "next_expense_created_at", "next_expense_date"],
    )


def downgrade() -> None:
    op.drop_table("recurring_expense_links")
    op.drop_table("activities")
    op.drop_table("expense_documents")
    op.drop_table("expense_paid_for")
    op.drop_table("expenses")
    op.drop_table("categories")
    op.drop_table("participants")
    op.drop_table("groups")

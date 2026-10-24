"""Authentication, membership and synchronization tables.

Sessions and verification tokens from the reference are intentionally not
created: users log in again with the new refresh-token flow.

Revision ID: 0003_sync_and_auth_schema
Revises: 0002_receipts_schema
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.models.types import UTCDateTime

revision = "0003_sync_and_auth_schema"
down_revision = "0002_receipts_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("email_verified", UTCDateTime(), nullable=True),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_updated_at", "users", ["updated_at"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("access_token", sa.String(), nullable=True),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("token_type", sa.String(length=64), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("id_token", sa.String(), nullable=True),
        sa.Column("session_state", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_accounts_provider_account",
        ),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
        sa.Column("replaced_by_id", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_refresh_tokens_revoked_at", "refresh_tokens", ["revoked_at"]
    )

    op.create_table(
        "user_groups",
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=64), primary_key=True),
        sa.Column("is_starred", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_groups_user_id", "user_groups", ["user_id"])
    op.create_index("ix_user_groups_group_id", "user_groups", ["group_id"])
    op.create_index("ix_user_groups_updated_at", "user_groups", ["updated_at"])
    op.create_index(
        "ix_user_groups_user_starred",
        "user_groups",
        ["user_id", "is_starred"],
    )

    op.create_table(
        "sync_changes",
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.String(length=64), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("op_type", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("changed_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_sync_changes_group_id", "sync_changes", ["group_id"])
    op.create_index(
        "ix_sync_changes_group_seq", "sync_changes", ["group_id", "seq"]
    )
    op.create_index(
        "ix_sync_changes_entity", "sync_changes", ["entity_type", "entity_id"]
    )
    op.create_index("ix_sync_changes_changed_at", "sync_changes", ["changed_at"])

    op.create_table(
        "sync_operations",
        sa.Column("op_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("applied_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_sync_operations_user_id", "sync_operations", ["user_id"])
    op.create_index(
        "ix_sync_operations_expires_at", "sync_operations", ["expires_at"]
    )

    op.create_table(
        "import_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("source_checksum", sa.String(length=64), nullable=False),
        sa.Column("target_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=False),
        sa.Column("finished_at", UTCDateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("counts_json", sa.Text(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_import_runs_source_checksum",
        "import_runs",
        ["source_checksum"],
    )


def downgrade() -> None:
    op.drop_table("import_runs")
    op.drop_table("sync_operations")
    op.drop_table("sync_changes")
    op.drop_table("user_groups")
    op.drop_table("refresh_tokens")
    op.drop_table("accounts")
    op.drop_table("users")

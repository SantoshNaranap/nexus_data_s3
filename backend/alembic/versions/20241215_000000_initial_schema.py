"""Initial database schema.

Revision ID: 001_initial
Revises: None
Create Date: 2024-12-15

This migration establishes the initial database schema for ConnectorMCP.
If tables already exist, this migration will be marked as complete.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table already exists in the database."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Create initial database tables if they don't exist."""

    # Create users table
    if not table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("profile_picture", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # Create chat_history table
    if not table_exists("chat_history"):
        op.create_table(
            "chat_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(255), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("session_id", sa.String(255), nullable=False, index=True),
            sa.Column("datasource", sa.String(50), nullable=False, index=True),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        # Create composite indexes
        op.create_index(
            "idx_user_datasource_created",
            "chat_history",
            ["user_id", "datasource", "created_at"]
        )
        op.create_index(
            "idx_user_session",
            "chat_history",
            ["user_id", "session_id"]
        )

    # Create user_credentials table
    if not table_exists("user_credentials"):
        op.create_table(
            "user_credentials",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("datasource", sa.String(50), nullable=False, index=True),
            sa.Column("encrypted_credentials", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )
        # Create unique constraint on user_id + datasource
        op.create_unique_constraint(
            "uq_user_datasource",
            "user_credentials",
            ["user_id", "datasource"]
        )


def downgrade() -> None:
    """Drop all tables (use with caution!)."""
    op.drop_table("user_credentials")
    op.drop_table("chat_history")
    op.drop_table("users")

"""Add security tables and fields.

Revision ID: 002_security
Revises: 001_initial
Create Date: 2024-12-15

Adds:
- login_attempts table for security auditing
- Security fields to users table (failed_login_attempts, locked_until, last_login_at)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "002_security"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    """Check if a table already exists in the database."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Add security tables and fields."""

    # Add security fields to users table if they don't exist
    if not column_exists("users", "failed_login_attempts"):
        op.add_column(
            "users",
            sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0")
        )

    if not column_exists("users", "locked_until"):
        op.add_column(
            "users",
            sa.Column("locked_until", sa.DateTime(), nullable=True)
        )

    if not column_exists("users", "last_login_at"):
        op.add_column(
            "users",
            sa.Column("last_login_at", sa.DateTime(), nullable=True)
        )

    # Create login_attempts table if it doesn't exist
    if not table_exists("login_attempts"):
        op.create_table(
            "login_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(255), nullable=False, index=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False),
            sa.Column("failure_reason", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        # Create indexes
        op.create_index(
            "idx_login_email_created",
            "login_attempts",
            ["email", "created_at"]
        )
        op.create_index(
            "idx_login_ip_created",
            "login_attempts",
            ["ip_address", "created_at"]
        )


def downgrade() -> None:
    """Remove security tables and fields."""
    # Drop login_attempts table
    op.drop_table("login_attempts")

    # Remove security columns from users
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")

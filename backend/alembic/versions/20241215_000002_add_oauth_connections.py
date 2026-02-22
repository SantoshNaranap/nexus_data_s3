"""Add OAuth connections table.

Revision ID: 003_oauth
Revises: 002_security
Create Date: 2024-12-15

Adds:
- oauth_connections table for storing OAuth tokens (Google, Slack, GitHub, etc.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "003_oauth"
down_revision: Union[str, None] = "002_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table already exists in the database."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Create oauth_connections table."""

    if not table_exists("oauth_connections"):
        op.create_table(
            "oauth_connections",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(50), nullable=False),  # google_workspace, slack, github
            sa.Column("provider_user_id", sa.String(255), nullable=True),  # Their ID on that provider
            sa.Column("provider_email", sa.String(255), nullable=True),  # Their email on that provider
            sa.Column("access_token", sa.Text(), nullable=False),  # Encrypted
            sa.Column("refresh_token", sa.Text(), nullable=True),  # Encrypted (Google has this, Slack doesn't)
            sa.Column("token_type", sa.String(50), nullable=False, server_default="Bearer"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),  # NULL if never expires (Slack)
            sa.Column("scopes", sa.Text(), nullable=True),  # JSON array of granted scopes
            sa.Column("extra_data", sa.Text(), nullable=True),  # JSON for provider-specific data
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )

        # Create indexes
        op.create_index(
            "idx_oauth_user_id",
            "oauth_connections",
            ["user_id"]
        )
        op.create_index(
            "idx_oauth_provider",
            "oauth_connections",
            ["provider"]
        )
        # Unique constraint: one connection per user per provider
        op.create_unique_constraint(
            "uq_user_provider",
            "oauth_connections",
            ["user_id", "provider"]
        )


def downgrade() -> None:
    """Drop oauth_connections table."""
    op.drop_table("oauth_connections")

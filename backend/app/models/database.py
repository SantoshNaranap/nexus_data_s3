"""Database models for multi-tenant support."""

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

Base = declarative_base()


class Tenant(Base):
    """Tenant/Organization model for multi-tenant support."""

    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, nullable=False, index=True)  # e.g., "kaaylabs.com"
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    users = relationship("User", back_populates="tenant")
    datasources = relationship("TenantDataSource", back_populates="tenant")

    def to_dict(self):
        """Convert tenant to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TenantDataSource(Base):
    """Tenant-level data source connections (organization-wide OAuth)."""

    __tablename__ = "tenant_datasources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    datasource = Column(String(50), nullable=False, index=True)  # "slack", "github", "jira"
    encrypted_credentials = Column(Text, nullable=False)  # OAuth tokens, encrypted
    oauth_metadata = Column(JSON, nullable=True)  # workspace_id, org_name, etc.
    connected_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Unique constraint: one datasource per tenant
    __table_args__ = (
        Index('idx_tenant_datasource', 'tenant_id', 'datasource', unique=True),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="datasources")
    connected_by_user = relationship("User", foreign_keys=[connected_by])

    def to_dict(self):
        """Convert tenant datasource to dictionary."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "datasource": self.datasource,
            "oauth_metadata": self.oauth_metadata,
            "connected_by": self.connected_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class User(Base):
    """User model for authentication (email/password or Google OAuth)."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for OAuth users
    name = Column(String(255), nullable=True)
    profile_picture = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    # Login tracking for "What You Missed" feature
    last_login = Column(DateTime, nullable=True)  # Current login timestamp
    previous_login = Column(DateTime, nullable=True)  # Previous login (for "since last login" queries)

    # Multi-tenant and OAuth fields
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    role = Column(String(20), default="member", nullable=False)  # 'admin' or 'member'
    auth_provider = Column(String(20), default="email", nullable=False)  # 'email' or 'google'
    google_id = Column(String(255), nullable=True, unique=True, index=True)  # Google OAuth user ID

    # Relationships
    tenant = relationship("Tenant", back_populates="users")

    def to_dict(self):
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "profile_picture": self.profile_picture,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "previous_login": self.previous_login.isoformat() if self.previous_login else None,
            "tenant_id": self.tenant_id,
            "role": self.role,
            "auth_provider": self.auth_provider,
        }

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin."""
        return self.role == "admin"


class ChatHistory(Base):
    """Chat history model for storing conversation messages per user."""

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    datasource = Column(String(50), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_user_datasource_created', 'user_id', 'datasource', 'created_at'),
        Index('idx_user_session', 'user_id', 'session_id'),
    )

    def __repr__(self):
        return f"<ChatHistory(id={self.id}, user_id={self.user_id}, role={self.role})>"

    def to_dict(self):
        """Convert to dictionary format compatible with chat service."""
        return {
            "role": self.role,
            "content": self.content,
        }


class UserCredential(Base):
    """User credentials model for storing encrypted datasource credentials."""

    __tablename__ = "user_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    datasource = Column(String(50), nullable=False, index=True)
    encrypted_credentials = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        """Convert user credential to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "datasource": self.datasource,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

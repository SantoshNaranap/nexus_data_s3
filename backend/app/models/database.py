"""Database models for multi-tenant support."""

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import uuid

Base = declarative_base()


class User(Base):
    """User model for authentication (email/password)."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    profile_picture = Column(Text, nullable=True)
    # Security fields
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def is_locked(self) -> bool:
        """Check if account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until

    def to_dict(self):
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "profile_picture": self.profile_picture,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LoginAttempt(Base):
    """Track login attempts for security monitoring."""

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_login_email_created', 'email', 'created_at'),
        Index('idx_login_ip_created', 'ip_address', 'created_at'),
    )


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


class OAuthConnection(Base):
    """OAuth connections for storing provider tokens (Google, Slack, GitHub, etc.)."""

    __tablename__ = "oauth_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)  # google_workspace, slack, github
    provider_user_id = Column(String(255), nullable=True)  # Their ID on that provider
    provider_email = Column(String(255), nullable=True)  # Their email on that provider
    access_token = Column(Text, nullable=False)  # Encrypted
    refresh_token = Column(Text, nullable=True)  # Encrypted (Google has this, Slack doesn't)
    token_type = Column(String(50), nullable=False, default="Bearer")
    expires_at = Column(DateTime, nullable=True)  # NULL if never expires (Slack)
    scopes = Column(Text, nullable=True)  # JSON array of granted scopes
    extra_data = Column(Text, nullable=True)  # JSON for provider-specific data
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Unique constraint: one connection per user per provider
    __table_args__ = (
        Index('idx_oauth_user_provider', 'user_id', 'provider', unique=True),
    )

    @property
    def is_expired(self) -> bool:
        """Check if access token is expired."""
        if self.expires_at is None:
            return False  # Never expires (e.g., Slack)
        return datetime.utcnow() >= self.expires_at

    @property
    def needs_refresh(self) -> bool:
        """Check if token should be refreshed (within 5 minutes of expiry)."""
        if self.expires_at is None:
            return False
        from datetime import timedelta
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))

    def to_dict(self):
        """Convert OAuth connection to dictionary (excludes sensitive tokens)."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "provider_email": self.provider_email,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scopes": self.scopes,
            "is_expired": self.is_expired,
            "needs_refresh": self.needs_refresh,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

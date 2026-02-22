"""
Security service for password validation, account lockout, and login tracking.

Provides enterprise-grade security features including:
- Password complexity validation
- Account lockout after failed attempts
- Login attempt tracking for security auditing
- IP-based rate limiting support
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User, LoginAttempt

logger = logging.getLogger(__name__)


class PasswordValidationError(Exception):
    """Raised when password doesn't meet complexity requirements."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class SecurityService:
    """Service for security-related operations."""

    @staticmethod
    def validate_password(password: str) -> Tuple[bool, List[str]]:
        """
        Validate password against complexity requirements.

        Args:
            password: The password to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if len(password) < settings.password_min_length:
            errors.append(
                f"Password must be at least {settings.password_min_length} characters"
            )

        if settings.password_require_uppercase and not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")

        if settings.password_require_lowercase and not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")

        if settings.password_require_digit and not re.search(r"\d", password):
            errors.append("Password must contain at least one digit")

        if settings.password_require_special and not re.search(
            r"[!@#$%^&*(),.?\":{}|<>]", password
        ):
            errors.append("Password must contain at least one special character")

        # Check for common weak passwords
        weak_passwords = [
            "password",
            "12345678",
            "qwerty123",
            "abc12345",
            "password1",
        ]
        if password.lower() in weak_passwords:
            errors.append("Password is too common. Please choose a stronger password")

        return len(errors) == 0, errors

    @staticmethod
    async def record_login_attempt(
        db: AsyncSession,
        email: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        """
        Record a login attempt for security auditing.

        Args:
            db: Database session
            email: Email address used in login attempt
            success: Whether the login was successful
            ip_address: Client IP address
            user_agent: Client user agent string
            failure_reason: Reason for failure if unsuccessful
        """
        attempt = LoginAttempt(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason,
        )
        db.add(attempt)
        await db.commit()

        if not success:
            logger.warning(
                f"Failed login attempt for {email} from {ip_address}: {failure_reason}"
            )

    @staticmethod
    async def check_account_locked(db: AsyncSession, email: str) -> Tuple[bool, Optional[datetime]]:
        """
        Check if an account is locked due to failed login attempts.

        Args:
            db: Database session
            email: User's email

        Returns:
            Tuple of (is_locked, locked_until datetime or None)
        """
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return False, None

        if user.is_locked:
            return True, user.locked_until

        return False, None

    @staticmethod
    async def increment_failed_attempts(db: AsyncSession, user: User) -> bool:
        """
        Increment failed login attempts and lock account if threshold exceeded.

        Args:
            db: Database session
            user: User object

        Returns:
            True if account is now locked, False otherwise
        """
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= settings.max_login_attempts:
            user.locked_until = datetime.utcnow() + timedelta(
                minutes=settings.lockout_duration_minutes
            )
            await db.commit()
            logger.warning(
                f"Account locked for {user.email} after {user.failed_login_attempts} failed attempts. "
                f"Locked until {user.locked_until}"
            )
            return True

        await db.commit()
        return False

    @staticmethod
    async def reset_failed_attempts(db: AsyncSession, user: User) -> None:
        """
        Reset failed login attempts after successful login.

        Args:
            db: Database session
            user: User object
        """
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.utcnow()
        await db.commit()

    @staticmethod
    async def get_recent_login_attempts(
        db: AsyncSession,
        email: str,
        hours: int = 24,
    ) -> List[LoginAttempt]:
        """
        Get recent login attempts for a user.

        Args:
            db: Database session
            email: User's email
            hours: Number of hours to look back

        Returns:
            List of LoginAttempt records
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        result = await db.execute(
            select(LoginAttempt)
            .where(LoginAttempt.email == email)
            .where(LoginAttempt.created_at >= since)
            .order_by(LoginAttempt.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_failed_attempts_by_ip(
        db: AsyncSession,
        ip_address: str,
        minutes: int = 15,
    ) -> int:
        """
        Count failed login attempts from an IP address.

        Args:
            db: Database session
            ip_address: Client IP address
            minutes: Time window to check

        Returns:
            Number of failed attempts
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)
        result = await db.execute(
            select(func.count(LoginAttempt.id))
            .where(LoginAttempt.ip_address == ip_address)
            .where(LoginAttempt.success == False)
            .where(LoginAttempt.created_at >= since)
        )
        return result.scalar() or 0

    @staticmethod
    async def cleanup_old_login_attempts(
        db: AsyncSession,
        days: int = 90,
    ) -> int:
        """
        Clean up old login attempt records.

        Args:
            db: Database session
            days: Delete records older than this many days

        Returns:
            Number of records deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            delete(LoginAttempt).where(LoginAttempt.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old login attempt records")
        return deleted


# Singleton instance
security_service = SecurityService()

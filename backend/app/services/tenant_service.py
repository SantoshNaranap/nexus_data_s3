"""Tenant management service for multi-tenant support."""

import logging
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.database import Tenant, User, TenantDataSource

logger = logging.getLogger(__name__)


class TenantService:
    """Service for managing tenants (organizations)."""

    @staticmethod
    def extract_domain_from_email(email: str) -> str:
        """Extract domain from email address."""
        if "@" not in email:
            raise ValueError(f"Invalid email format: {email}")
        return email.split("@")[1].lower()

    @staticmethod
    async def get_tenant_by_domain(db: AsyncSession, domain: str) -> Optional[Tenant]:
        """Get tenant by domain."""
        result = await db.execute(
            select(Tenant).where(Tenant.domain == domain.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tenant_by_id(db: AsyncSession, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID."""
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant(db: AsyncSession, domain: str, name: Optional[str] = None) -> Tenant:
        """Create a new tenant for a domain."""
        if name is None:
            # Default name to capitalized domain without TLD
            name = domain.split(".")[0].capitalize()

        tenant = Tenant(domain=domain.lower(), name=name)
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

        logger.info(f"Created new tenant: {tenant.name} ({tenant.domain})")
        return tenant

    @staticmethod
    async def get_or_create_tenant(db: AsyncSession, domain: str) -> Tenant:
        """Get existing tenant or create a new one for the domain."""
        tenant = await TenantService.get_tenant_by_domain(db, domain)
        if tenant:
            return tenant
        return await TenantService.create_tenant(db, domain)

    @staticmethod
    async def get_tenant_user_count(db: AsyncSession, tenant_id: str) -> int:
        """Get the number of users in a tenant."""
        result = await db.execute(
            select(func.count(User.id)).where(User.tenant_id == tenant_id)
        )
        return result.scalar() or 0

    @staticmethod
    async def is_first_user_for_tenant(db: AsyncSession, tenant_id: str) -> bool:
        """Check if this would be the first user for a tenant."""
        count = await TenantService.get_tenant_user_count(db, tenant_id)
        return count == 0

    @staticmethod
    async def get_tenant_users(db: AsyncSession, tenant_id: str) -> List[User]:
        """Get all users in a tenant."""
        result = await db.execute(
            select(User).where(User.tenant_id == tenant_id).order_by(User.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_tenant_admins(db: AsyncSession, tenant_id: str) -> List[User]:
        """Get all admins in a tenant."""
        result = await db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.role == "admin"
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def assign_user_to_tenant(
        db: AsyncSession,
        user: User,
        tenant: Tenant,
        role: Optional[str] = None
    ) -> User:
        """
        Assign a user to a tenant.

        If role is not specified:
        - First user becomes admin
        - Subsequent users become members
        """
        if role is None:
            is_first = await TenantService.is_first_user_for_tenant(db, tenant.id)
            role = "admin" if is_first else "member"

        user.tenant_id = tenant.id
        user.role = role

        await db.commit()
        await db.refresh(user)

        logger.info(f"Assigned user {user.email} to tenant {tenant.domain} as {role}")
        return user

    @staticmethod
    async def promote_to_admin(db: AsyncSession, user: User) -> User:
        """Promote a user to admin role."""
        user.role = "admin"
        await db.commit()
        await db.refresh(user)
        logger.info(f"Promoted user {user.email} to admin")
        return user

    @staticmethod
    async def demote_to_member(db: AsyncSession, user: User) -> User:
        """Demote a user to member role."""
        user.role = "member"
        await db.commit()
        await db.refresh(user)
        logger.info(f"Demoted user {user.email} to member")
        return user

    @staticmethod
    async def get_tenant_with_datasources(db: AsyncSession, tenant_id: str) -> Optional[Tenant]:
        """Get tenant with all connected datasources loaded."""
        result = await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .options(selectinload(Tenant.datasources))
        )
        return result.scalar_one_or_none()


# Singleton instance for convenience
tenant_service = TenantService()

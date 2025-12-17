"""
Chat history service with pagination, limits, and cleanup.

Manages chat message storage with:
- Pagination for retrieving history
- Per-session message limits
- Automatic cleanup of old messages
- Per-user session limits
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import ChatHistory

logger = logging.getLogger(__name__)


class ChatHistoryService:
    """Service for managing chat history with pagination and limits."""

    def __init__(self):
        self.max_messages_per_session = settings.chat_max_messages_per_session
        self.max_sessions_per_user = settings.chat_max_sessions_per_user
        self.retention_days = settings.chat_history_retention_days

    async def add_message(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        datasource: str,
        role: str,
        content: str,
    ) -> ChatHistory:
        """
        Add a message to chat history.

        Enforces per-session message limits by removing oldest messages.

        Args:
            db: Database session
            user_id: User ID
            session_id: Chat session ID
            datasource: Data source identifier
            role: Message role ('user' or 'assistant')
            content: Message content

        Returns:
            Created ChatHistory record
        """
        # Create new message
        message = ChatHistory(
            user_id=user_id,
            session_id=session_id,
            datasource=datasource,
            role=role,
            content=content,
        )
        db.add(message)
        await db.flush()

        # Enforce message limit per session
        await self._enforce_session_limit(db, user_id, session_id)

        await db.commit()
        return message

    async def get_messages(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
        order_desc: bool = False,
    ) -> Dict[str, Any]:
        """
        Get paginated messages for a session.

        Args:
            db: Database session
            user_id: User ID
            session_id: Chat session ID
            limit: Maximum messages to return
            offset: Number of messages to skip
            order_desc: If True, return newest first

        Returns:
            Dict with messages, total count, and pagination info
        """
        # Get total count
        count_result = await db.execute(
            select(func.count(ChatHistory.id)).where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == session_id,
                )
            )
        )
        total = count_result.scalar() or 0

        # Get messages with pagination
        order_by = ChatHistory.created_at.desc() if order_desc else ChatHistory.created_at.asc()
        result = await db.execute(
            select(ChatHistory)
            .where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == session_id,
                )
            )
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
        )
        messages = list(result.scalars().all())

        return {
            "messages": [msg.to_dict() for msg in messages],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(messages) < total,
        }

    async def get_recent_messages(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Get most recent messages for context (for LLM).

        Args:
            db: Database session
            user_id: User ID
            session_id: Chat session ID
            limit: Max messages to return (defaults to config value)

        Returns:
            List of message dicts in chronological order
        """
        if limit is None:
            limit = self.max_messages_per_session

        result = await db.execute(
            select(ChatHistory)
            .where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == session_id,
                )
            )
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())

        # Return in chronological order
        return [msg.to_dict() for msg in reversed(messages)]

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        datasource: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get list of chat sessions for a user.

        Args:
            db: Database session
            user_id: User ID
            datasource: Optional datasource filter
            limit: Max sessions to return
            offset: Number of sessions to skip

        Returns:
            Dict with sessions and pagination info
        """
        # Build base query
        base_filter = ChatHistory.user_id == user_id
        if datasource:
            base_filter = and_(base_filter, ChatHistory.datasource == datasource)

        # Get distinct sessions with latest message time
        subquery = (
            select(
                ChatHistory.session_id,
                ChatHistory.datasource,
                func.max(ChatHistory.created_at).label("last_message_at"),
                func.count(ChatHistory.id).label("message_count"),
            )
            .where(base_filter)
            .group_by(ChatHistory.session_id, ChatHistory.datasource)
            .subquery()
        )

        # Get total count
        count_result = await db.execute(
            select(func.count()).select_from(subquery)
        )
        total = count_result.scalar() or 0

        # Get paginated sessions
        result = await db.execute(
            select(subquery)
            .order_by(subquery.c.last_message_at.desc())
            .offset(offset)
            .limit(limit)
        )
        sessions = [
            {
                "session_id": row.session_id,
                "datasource": row.datasource,
                "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
                "message_count": row.message_count,
            }
            for row in result.all()
        ]

        return {
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(sessions) < total,
        }

    async def delete_session(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
    ) -> int:
        """
        Delete all messages in a session.

        Args:
            db: Database session
            user_id: User ID
            session_id: Session to delete

        Returns:
            Number of messages deleted
        """
        result = await db.execute(
            delete(ChatHistory).where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == session_id,
                )
            )
        )
        await db.commit()
        deleted = result.rowcount
        logger.info(f"Deleted {deleted} messages from session {session_id[:8]}...")
        return deleted

    async def cleanup_old_messages(self, db: AsyncSession) -> int:
        """
        Delete messages older than retention period.

        Should be called periodically via background task.

        Returns:
            Number of messages deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        result = await db.execute(
            delete(ChatHistory).where(ChatHistory.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} messages older than {self.retention_days} days")
        return deleted

    async def _enforce_session_limit(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
    ) -> int:
        """
        Enforce per-session message limit by removing oldest messages.

        Returns:
            Number of messages deleted
        """
        # Get current count
        count_result = await db.execute(
            select(func.count(ChatHistory.id)).where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == session_id,
                )
            )
        )
        count = count_result.scalar() or 0

        if count <= self.max_messages_per_session:
            return 0

        # Calculate how many to delete
        to_delete = count - self.max_messages_per_session

        # Get IDs of oldest messages
        oldest_result = await db.execute(
            select(ChatHistory.id)
            .where(
                and_(
                    ChatHistory.user_id == user_id,
                    ChatHistory.session_id == session_id,
                )
            )
            .order_by(ChatHistory.created_at.asc())
            .limit(to_delete)
        )
        ids_to_delete = [row[0] for row in oldest_result.all()]

        if ids_to_delete:
            await db.execute(
                delete(ChatHistory).where(ChatHistory.id.in_(ids_to_delete))
            )
            logger.debug(f"Deleted {len(ids_to_delete)} old messages from session {session_id[:8]}...")

        return len(ids_to_delete)

    async def _enforce_user_session_limit(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> int:
        """
        Enforce per-user session limit by removing oldest sessions.

        Returns:
            Number of sessions deleted
        """
        # Get session counts ordered by last message
        sessions = await self.get_user_sessions(db, user_id, limit=1000)

        if sessions["total"] <= self.max_sessions_per_user:
            return 0

        # Delete oldest sessions beyond limit
        sessions_to_delete = sessions["sessions"][self.max_sessions_per_user:]
        deleted_count = 0

        for session_info in sessions_to_delete:
            deleted = await self.delete_session(db, user_id, session_info["session_id"])
            deleted_count += 1

        logger.info(f"Deleted {deleted_count} old sessions for user {user_id[:8]}...")
        return deleted_count


# Singleton instance
chat_history_service = ChatHistoryService()

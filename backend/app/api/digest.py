"""
Digest API endpoints for "What You Missed" feature.

Provides endpoints to generate personalized digests of updates
across all connected data sources since the user's last login.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.database import User
from app.services.digest_service import digest_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/digest", tags=["Digest"])


# ============ Request/Response Models ============


class DigestRequest(BaseModel):
    """Request model for digest generation."""
    since: Optional[datetime] = None  # Defaults to previous_login
    sources: Optional[List[str]] = None  # Defaults to all configured sources


class SourceResult(BaseModel):
    """Result from a single source query."""
    datasource: str
    success: bool
    summary: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None


class DigestResponse(BaseModel):
    """Response model for digest."""
    since: Optional[str]
    results: List[dict]
    summary: str
    successful_sources: List[str]
    failed_sources: List[str]
    total_time_ms: float


# ============ Endpoints ============


@router.post("/what-you-missed", response_model=DigestResponse)
async def get_what_you_missed(
    request: DigestRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a digest of updates since last login.

    Returns a summary of all updates across connected data sources
    since the user's previous login (or specified timestamp).

    If no 'since' timestamp is provided, uses the user's previous_login.
    If no previous_login exists, defaults to last 24 hours.
    """
    # Determine the 'since' timestamp
    since = None
    if request and request.since:
        since = request.since
    elif current_user.previous_login:
        since = current_user.previous_login
    # If neither, digest_service will default to 24 hours

    # Get sources to query
    sources = request.sources if request else None

    logger.info(
        f"Generating digest for user {current_user.email} "
        f"since {since or 'default (24h)'}, sources: {sources or 'all'}"
    )

    try:
        result = await digest_service.generate_digest(
            db=db,
            user_id=current_user.id,
            since=since,
            sources=sources,
        )

        return DigestResponse(
            since=result["since"],
            results=result["results"],
            summary=result["summary"],
            successful_sources=result["successful_sources"],
            failed_sources=result["failed_sources"],
            total_time_ms=result["total_time_ms"],
        )

    except Exception as e:
        logger.error(f"Error generating digest: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate digest: {str(e)}",
        )


@router.get("/sources")
async def get_configured_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of data sources the user has configured.

    Returns the sources that will be queried for the digest.
    """
    sources = await digest_service.get_configured_sources(db, current_user.id)

    return {
        "sources": sources,
        "count": len(sources),
    }


@router.get("/last-login")
async def get_last_login_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get user's login timestamp information.

    Returns last_login and previous_login timestamps for display.
    """
    return {
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
        "previous_login": current_user.previous_login.isoformat() if current_user.previous_login else None,
        "has_previous_login": current_user.previous_login is not None,
    }

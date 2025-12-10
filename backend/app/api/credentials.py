"""Credentials API endpoints."""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.credential_service import credential_service
from app.middleware.auth import get_current_user_optional as get_current_user
from app.core.database import get_db
from app.models.database import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


class CredentialsSaveRequest(BaseModel):
    """Request model for saving credentials."""
    datasource: str
    credentials: Dict[str, str]


class CredentialsResponse(BaseModel):
    """Response model for credentials operations."""
    success: bool
    message: str
    datasource: str


@router.post("", response_model=CredentialsResponse)
async def save_credentials(
    request: CredentialsSaveRequest,
    response: Response,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save credentials for a datasource.

    For authenticated users: Credentials are stored in AWS Secrets Manager.
    For anonymous users: Credentials are stored in-memory per session.
    """
    try:
        if user:
            # Authenticated user - save to database
            await credential_service.save_credentials(
                datasource=request.datasource,
                credentials=request.credentials,
                db=db,
                user_id=user.id,
            )
            logger.info(f"Credentials saved for user {user.id[:8]}... datasource: {request.datasource}")
        else:
            # Anonymous user - use session-based storage
            session_id = req.cookies.get("session_id")
            if not session_id:
                # Generate new session ID
                import secrets
                session_id = secrets.token_urlsafe(32)
                response.set_cookie(
                    key="session_id",
                    value=session_id,
                    httponly=True,
                    samesite="lax",
                    max_age=86400,  # 24 hours
                )

            await credential_service.save_credentials(
                datasource=request.datasource,
                credentials=request.credentials,
                session_id=session_id,
            )
            logger.info(f"Credentials saved for session {session_id[:8]}... datasource: {request.datasource}")

        return CredentialsResponse(
            success=True,
            message="Credentials saved successfully",
            datasource=request.datasource,
        )

    except Exception as e:
        logger.error(f"Error saving credentials: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save credentials: {str(e)}",
        )


@router.get("/{datasource}/status")
async def get_credentials_status(
    datasource: str,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if credentials are configured for a datasource."""
    try:
        if user:
            # Check for authenticated user
            has_credentials = await credential_service.has_credentials(
                datasource=datasource,
                db=db,
                user_id=user.id,
            )
        else:
            # Check for anonymous user
            session_id = req.cookies.get("session_id")
            if not session_id:
                return {"configured": False}

            has_credentials = await credential_service.has_credentials(
                datasource=datasource,
                session_id=session_id,
            )

        return {"configured": has_credentials}

    except Exception as e:
        logger.error(f"Error checking credentials status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check credentials status: {str(e)}",
        )


@router.delete("/{datasource}")
async def delete_credentials(
    datasource: str,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete credentials for a datasource."""
    try:
        if user:
            # Delete for authenticated user
            await credential_service.delete_credentials(
                datasource=datasource,
                db=db,
                user_id=user.id,
            )
            logger.info(f"Credentials deleted for user {user.id[:8]}... datasource: {datasource}")
        else:
            # Delete for anonymous user
            session_id = req.cookies.get("session_id")
            if not session_id:
                raise HTTPException(
                    status_code=404,
                    detail="No session found",
                )

            await credential_service.delete_credentials(
                datasource=datasource,
                session_id=session_id,
            )
            logger.info(f"Credentials deleted for session {session_id[:8]}... datasource: {datasource}")

        return {
            "success": True,
            "message": "Credentials deleted successfully",
        }

    except Exception as e:
        logger.error(f"Error deleting credentials: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete credentials: {str(e)}",
        )

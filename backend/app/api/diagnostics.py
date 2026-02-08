"""
Diagnostics API endpoints for error investigation.

Provides automatic error detection and diagnosis capabilities.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.middleware.auth import get_current_user_optional
from app.models.database import User
from app.services.error_investigation_service import error_investigation_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])


# ============ Request/Response Models ============


class ErrorInvestigationRequest(BaseModel):
    """Request model for error investigation."""
    error_message: str = Field(..., min_length=1, description="The error message to investigate")
    datasource: str = Field(..., description="The datasource that caused the error")
    user_query: Optional[str] = Field(None, description="The original user query")
    session_id: Optional[str] = Field(None, description="Session ID for anonymous users")


class InvestigationFindingResponse(BaseModel):
    """Response model for a single investigation finding."""
    category: str
    severity: str
    title: str
    detail: str
    suggested_action: Optional[str] = None


class ErrorInvestigationResponse(BaseModel):
    """Response model for error investigation."""
    investigation_id: str
    status: str
    root_cause: Optional[str] = None
    findings: list[InvestigationFindingResponse]
    recommendations: list[str]
    investigated_at: str
    duration_ms: int


# ============ Endpoints ============


@router.post("/investigate", response_model=ErrorInvestigationResponse)
async def investigate_error(
    request: ErrorInvestigationRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Investigate an error and provide diagnosis.

    This endpoint analyzes error messages and checks:
    1. Circuit breaker status - Is datasource circuit open due to failures?
    2. Credential validation - Do credentials exist? Are OAuth tokens expired?
    3. MCP connection test - Can we connect to the MCP server?
    4. Error pattern classification - What type of error is this?

    Returns findings with severity levels and recommendations for fixing the issue.
    """
    logger.info(
        f"Investigation request for {request.datasource}",
        extra={
            "datasource": request.datasource,
            "user_id": user.id if user else None,
            "has_session_id": bool(request.session_id),
        },
    )

    try:
        # Run investigation with timeout
        result = await asyncio.wait_for(
            error_investigation_service.investigate(
                error_message=request.error_message,
                datasource=request.datasource,
                user_id=user.id if user else None,
                db=db,
                session_id=request.session_id,
            ),
            timeout=10.0,  # Max 10 seconds for the entire investigation
        )

        logger.info(
            f"Investigation completed: {result.investigation_id}",
            extra={
                "investigation_id": result.investigation_id,
                "status": result.status,
                "findings_count": len(result.findings),
                "duration_ms": result.duration_ms,
            },
        )

        return result.to_dict()

    except asyncio.TimeoutError:
        logger.error(f"Investigation timed out for {request.datasource}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Investigation timed out",
        )
    except Exception as e:
        logger.error(f"Investigation failed for {request.datasource}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {str(e)}",
        )


class RemediationRequest(BaseModel):
    """Request model for auto-remediation."""
    datasource: str = Field(..., description="The datasource to fix")
    session_id: Optional[str] = Field(None, description="Session ID for anonymous users")


class RemediationActionResponse(BaseModel):
    """Response model for a single remediation action."""
    action: str
    success: bool
    detail: str


class RemediationResponse(BaseModel):
    """Response model for remediation attempt."""
    status: str  # 'fixed', 'partial', 'failed'
    message: str
    actions: list[RemediationActionResponse]
    connection_restored: bool
    duration_ms: int


@router.post("/remediate", response_model=RemediationResponse)
async def remediate_error(
    request: RemediationRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Attempt to automatically fix a datasource issue.

    This endpoint:
    1. Resets circuit breakers
    2. Refreshes OAuth tokens
    3. Clears stale tool caches
    4. Tests the connection to verify the fix

    Returns the status of each action and whether the connection was restored.
    """
    logger.info(
        f"Remediation request for {request.datasource}",
        extra={"datasource": request.datasource, "user_id": user.id if user else None},
    )

    try:
        result = await asyncio.wait_for(
            error_investigation_service.remediate(
                datasource=request.datasource,
                user_id=user.id if user else None,
                db=db,
                session_id=request.session_id,
            ),
            timeout=30.0,
        )

        logger.info(
            f"Remediation completed: {result.status}",
            extra={
                "status": result.status,
                "connection_restored": result.connection_restored,
                "duration_ms": result.duration_ms,
            },
        )

        return result.to_dict()

    except asyncio.TimeoutError:
        logger.error(f"Remediation timed out for {request.datasource}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Remediation timed out",
        )
    except Exception as e:
        logger.error(f"Remediation failed for {request.datasource}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remediation failed: {str(e)}",
        )


@router.get("/circuit-breakers")
async def get_circuit_breakers():
    """
    Get the status of all circuit breakers.

    Returns the current state of all MCP circuit breakers including:
    - State (closed, open, half-open)
    - Failure counts
    - Time until retry (if open)
    """
    from app.services.circuit_breaker import mcp_circuit_breakers

    return {
        "circuit_breakers": mcp_circuit_breakers.get_all_stats(),
    }


@router.post("/circuit-breakers/{datasource}/reset")
async def reset_circuit_breaker(
    datasource: str,
    user: User = Depends(get_current_user_optional),
):
    """
    Reset a circuit breaker for a specific datasource.

    This allows manually recovering from a circuit breaker open state.
    Requires authentication.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    from app.services.circuit_breaker import mcp_circuit_breakers

    breaker_name = f"mcp_{datasource}"
    success = mcp_circuit_breakers.reset(breaker_name)

    if success:
        logger.info(f"Circuit breaker {breaker_name} reset by user {user.id}")
        return {"message": f"Circuit breaker for {datasource} has been reset"}
    else:
        return {"message": f"No circuit breaker found for {datasource}"}

"""
Agent API Routes for Multi-Source Queries.

This module provides REST API endpoints for the agent orchestration system,
enabling multi-source queries through a unified interface.

Endpoints:
- POST /api/agent/query - Execute a multi-source query
- POST /api/agent/query/stream - Execute with streaming response
- POST /api/agent/suggest - Get source suggestions for a query
- POST /api/agent/detect - Check if query needs multiple sources
"""

import logging
import json
from fastapi import APIRouter, HTTPException, Request, Depends, Body
from fastapi.responses import StreamingResponse
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_service import agent_orchestrator
from app.middleware.auth import get_current_user_optional as get_current_user
from app.core.database import get_db
from app.models.database import User
from app.models.agent import (
    MultiSourceRequest,
    MultiSourceResponse,
    DataSourceRelevance,
    AgentStreamEvent,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/query", response_model=MultiSourceResponse)
async def execute_multi_source_query(
    request: MultiSourceRequest,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a multi-source query and return synthesized results.
    
    This endpoint analyzes the query, determines relevant data sources,
    executes queries in parallel, and synthesizes the results into a
    unified response.
    
    Args:
        request: MultiSourceRequest containing:
            - query: Natural language query
            - sources: Optional list of specific sources to query
            - session_id: Optional session ID for context
            - confidence_threshold: Minimum confidence for auto-detected sources
            - max_sources: Maximum number of sources to query
            - include_plan: Whether to include execution plan in response
    
    Returns:
        MultiSourceResponse with:
            - response: Synthesized natural language response
            - status: Overall execution status
            - plan: Execution plan (if requested)
            - source_results: Individual results from each source
            - successful_sources: List of sources that succeeded
            - failed_sources: List of sources that failed
            - total_execution_time_ms: Total time taken
    
    Example:
        ```json
        POST /api/agent/query
        {
            "query": "What are my latest JIRA tasks and recent emails?",
            "max_sources": 2,
            "include_plan": true
        }
        ```
    """
    try:
        # Get credential session ID from cookies (for anonymous users)
        credential_session_id = req.cookies.get("session_id")
        
        # Use user_id for credentials if authenticated
        if user:
            credential_session_id = user.id
        
        logger.info(f"Multi-source query request: {request.query[:100]}...")
        
        # Execute the multi-source query
        response = await agent_orchestrator.process_multi_source_query(
            request=request,
            user_id=user.id if user else None,
            credential_session_id=credential_session_id,
            db=db if user else None,
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Multi-source query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def execute_multi_source_query_stream(
    request: MultiSourceRequest,
    req: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a multi-source query with streaming progress updates.
    
    This endpoint streams Server-Sent Events (SSE) as the query progresses
    through planning, execution, and synthesis phases. Ideal for real-time
    UI updates.
    
    Event Types:
        - started: Query processing has begun
        - planning: Creating execution plan
        - plan_complete: Plan is ready, shows which sources will be queried
        - executing: Starting to query data sources
        - source_start: Beginning to query a specific source
        - source_complete: Finished querying a source (success or failure)
        - synthesizing: Combining results
        - synthesis_chunk: Streaming chunk of synthesized response
        - done: Query completed successfully
        - error: An error occurred
    
    Returns:
        StreamingResponse with SSE events
    
    Example SSE stream:
        ```
        data: {"event_type": "started", "message": "🔍 Analyzing your query..."}
        data: {"event_type": "plan_complete", "data": {"sources": ["jira", "gmail"]}}
        data: {"event_type": "source_start", "data": {"datasource": "jira"}}
        data: {"event_type": "source_complete", "data": {"datasource": "jira", "success": true}}
        data: {"event_type": "synthesis_chunk", "data": {"content": "Based on your..."}}
        data: {"event_type": "done", "data": {"total_time_ms": 3500}}
        ```
    """
    try:
        # Get credential session ID from cookies
        credential_session_id = req.cookies.get("session_id")
        
        if user:
            credential_session_id = user.id
        
        async def event_generator():
            """Generate Server-Sent Events for query progress."""
            try:
                # Stream events from the agent orchestrator
                async for event in agent_orchestrator.process_multi_source_query_stream(
                    request=request,
                    user_id=user.id if user else None,
                    credential_session_id=credential_session_id,
                    db=db if user else None,
                ):
                    # Format as SSE
                    event_data = {
                        "event_type": event.event_type,
                        "data": event.data,
                        "message": event.message,
                        "timestamp": event.timestamp.isoformat(),
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    
            except Exception as e:
                logger.error(f"Stream error: {e}")
                error_event = {
                    "event_type": "error",
                    "data": {"error": str(e)},
                    "message": f"Error: {str(e)}",
                }
                yield f"data: {json.dumps(error_event)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
        
    except Exception as e:
        logger.error(f"Stream setup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggest", response_model=List[DataSourceRelevance])
async def suggest_sources(
    query: str,
    max_suggestions: int = 5,
):
    """
    Get source suggestions for a query without executing it.
    
    Useful for UI previews, query planning, or helping users understand
    which data sources will be queried.
    
    Args:
        query: The natural language query to analyze
        max_suggestions: Maximum number of source suggestions (default 5)
    
    Returns:
        List of DataSourceRelevance with:
            - datasource: Source identifier
            - confidence: Relevance score (0-1)
            - reasoning: Why this source is relevant
            - suggested_approach: How to query this source
    
    Example:
        ```json
        POST /api/agent/suggest
        {
            "query": "Show me all bugs assigned to John",
            "max_suggestions": 3
        }
        
        Response:
        [
            {
                "datasource": "jira",
                "confidence": 0.95,
                "reasoning": "Keywords matched: bugs, assigned",
                "suggested_approach": "Use query_jira with natural language"
            }
        ]
        ```
    """
    try:
        suggestions = await agent_orchestrator.suggest_sources(
            query=query,
            max_suggestions=max_suggestions,
        )
        return suggestions
        
    except Exception as e:
        logger.error(f"Source suggestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect")
async def detect_multi_source(query: str = Body(..., embed=True)):
    """
    Detect if a query should use multi-source processing.
    
    Quickly analyzes the query to determine if it would benefit from
    querying multiple data sources simultaneously.
    
    Args:
        query: The natural language query to analyze
    
    Returns:
        Dict with:
            - is_multi_source: Whether multi-source is recommended
            - suggested_sources: List of potentially relevant sources
    
    Example:
        ```json
        POST /api/agent/detect
        {
            "query": "Compare my JIRA tasks with recent emails"
        }
        
        Response:
        {
            "is_multi_source": true,
            "suggested_sources": ["jira", "google_workspace"],
            "reasoning": "Query mentions both JIRA tasks and emails"
        }
        ```
    """
    try:
        # Check if multi-source processing is appropriate
        is_multi_source = await agent_orchestrator.detect_if_multi_source(query)
        
        # Get source suggestions
        suggestions = await agent_orchestrator.suggest_sources(query, max_suggestions=3)
        
        return {
            "is_multi_source": is_multi_source,
            "suggested_sources": [s.datasource for s in suggestions],
            "sources_with_confidence": [
                {"datasource": s.datasource, "confidence": s.confidence}
                for s in suggestions
            ],
            "reasoning": "Query appears to reference multiple data types" if is_multi_source
                        else "Query can be handled by a single source",
        }
        
    except Exception as e:
        logger.error(f"Multi-source detection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def get_available_sources():
    """
    Get list of all available data sources for multi-source queries.
    
    Returns metadata about each configured data source including
    its capabilities and status.
    
    Returns:
        List of available data sources with:
            - id: Source identifier
            - name: Human-readable name
            - description: What this source provides
            - enabled: Whether source is currently available
    
    Example Response:
        ```json
        [
            {
                "id": "jira",
                "name": "JIRA",
                "description": "Project management and issue tracking",
                "enabled": true
            },
            {
                "id": "s3",
                "name": "Amazon S3",
                "description": "Cloud object storage",
                "enabled": true
            }
        ]
        ```
    """
    from app.services.mcp_service import mcp_service
    return mcp_service.get_available_datasources()








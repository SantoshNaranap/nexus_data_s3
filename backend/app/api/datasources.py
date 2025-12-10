"""Data sources API routes."""

from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.datasource import DataSource, DataSourceTest
from app.services.mcp_service import mcp_service
from app.middleware.auth import get_current_user_optional
from app.models.database import User
from app.core.database import get_db

router = APIRouter(prefix="/api/datasources", tags=["datasources"])


@router.get("", response_model=List[DataSource])
async def list_datasources():
    """List all available data sources."""
    return mcp_service.get_available_datasources()


@router.api_route("/{datasource_id}/test", methods=["GET", "POST"], response_model=DataSourceTest)
async def test_datasource(
    datasource_id: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Test connection to a specific data source.

    Accepts both GET and POST methods:
    - GET: Test with existing stored credentials
    - POST: Test after setting credentials (credentials in request body)
    """
    try:
        # Use user_id for authenticated users, session_id for anonymous
        if user:
            result = await mcp_service.test_connection(
                datasource_id,
                user_id=user.id,
                db=db
            )
        else:
            # Get credential session ID from cookies for anonymous users
            credential_session_id = request.cookies.get("session_id")
            result = await mcp_service.test_connection(
                datasource_id,
                session_id=credential_session_id
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

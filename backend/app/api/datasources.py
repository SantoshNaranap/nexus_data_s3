"""Data sources API routes."""

from fastapi import APIRouter, HTTPException
from typing import List

from app.models.datasource import DataSource, DataSourceTest
from app.services.mcp_service import mcp_service

router = APIRouter(prefix="/api/datasources", tags=["datasources"])


@router.get("", response_model=List[DataSource])
async def list_datasources():
    """List all available data sources."""
    return mcp_service.get_available_datasources()


@router.get("/{datasource_id}/test", response_model=DataSourceTest)
async def test_datasource(datasource_id: str):
    """Test connection to a specific data source."""
    try:
        result = await mcp_service.test_connection(datasource_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

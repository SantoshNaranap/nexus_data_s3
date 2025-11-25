"""Data source models."""

from pydantic import BaseModel, Field
from typing import List


class DataSource(BaseModel):
    """Data source model."""

    id: str = Field(..., description="Data source identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Data source description")
    icon: str = Field(..., description="Icon identifier")
    enabled: bool = Field(default=True, description="Whether the data source is enabled")


class DataSourceTest(BaseModel):
    """Data source connection test result."""

    datasource: str
    connected: bool
    message: str
    details: dict = {}

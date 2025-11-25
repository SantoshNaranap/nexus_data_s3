"""Chat models."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ChatMessage(BaseModel):
    """Chat message model."""

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., description="User message")
    datasource: str = Field(..., description="Data source to query (s3, mysql, jira, shopify)")
    session_id: Optional[str] = Field(None, description="Session ID for conversation history")


class ChatResponse(BaseModel):
    """Chat response model."""

    message: str = Field(..., description="Assistant response")
    session_id: str = Field(..., description="Session ID")
    datasource: str = Field(..., description="Data source used")
    tool_calls: Optional[List[dict]] = Field(None, description="Tools called during processing")


class SessionCreate(BaseModel):
    """Session creation model."""

    datasource: str = Field(..., description="Data source for this session")
    name: Optional[str] = Field(None, description="Optional session name")


class Session(BaseModel):
    """Session model."""

    id: str
    datasource: str
    name: Optional[str]
    created_at: datetime
    messages: List[ChatMessage] = []

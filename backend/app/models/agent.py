"""
Agent orchestration models for multi-source queries.

This module defines Pydantic models for the agent system that enables
querying across multiple data sources simultaneously.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class AgentTaskStatus(str, Enum):
    """
    Status of an agent task execution.
    
    Tracks the lifecycle of a task from pending through completion or failure.
    """
    PENDING = "pending"          # Task is queued but not started
    PLANNING = "planning"        # Agent is analyzing which sources to query
    EXECUTING = "executing"      # Queries are being executed
    SYNTHESIZING = "synthesizing"  # Results are being combined
    COMPLETED = "completed"      # Task finished successfully
    FAILED = "failed"           # Task encountered an error
    PARTIAL = "partial"         # Some sources succeeded, some failed


class DataSourceRelevance(BaseModel):
    """
    Represents the relevance of a data source for a given query.
    
    Used by the source detector to rank which sources should be queried.
    """
    # The data source identifier (e.g., "jira", "s3", "mysql")
    datasource: str = Field(..., description="Data source identifier")
    
    # Confidence score from 0.0 to 1.0 indicating relevance
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Confidence score for relevance (0-1)"
    )
    
    # Reason why this source is relevant
    reasoning: str = Field(..., description="Why this source is relevant")
    
    # Suggested query or approach for this source
    suggested_approach: Optional[str] = Field(
        None, 
        description="Suggested query approach for this source"
    )


class SourceQueryResult(BaseModel):
    """
    Result from querying a single data source.
    
    Encapsulates the response, timing, and any errors from a source query.
    """
    # The data source that was queried
    datasource: str = Field(..., description="Data source queried")
    
    # Whether the query succeeded
    success: bool = Field(..., description="Whether query succeeded")
    
    # The actual data returned (JSON-serializable)
    data: Optional[Any] = Field(None, description="Query result data")
    
    # Human-readable summary of the result
    summary: Optional[str] = Field(None, description="Summary of results")
    
    # Error message if query failed
    error: Optional[str] = Field(None, description="Error message if failed")
    
    # Tools that were called during this query
    tools_called: List[str] = Field(
        default_factory=list, 
        description="Tools called during query"
    )
    
    # Time taken to execute this query in milliseconds
    execution_time_ms: Optional[float] = Field(
        None, 
        description="Execution time in milliseconds"
    )
    
    # Timestamp when this result was generated
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, 
        description="When result was generated"
    )


class AgentPlan(BaseModel):
    """
    Execution plan created by the agent for a multi-source query.
    
    Describes which sources will be queried and in what order.
    """
    # Original user query
    original_query: str = Field(..., description="Original user query")
    
    # Detected sources ranked by relevance
    relevant_sources: List[DataSourceRelevance] = Field(
        ..., 
        description="Relevant sources ranked by confidence"
    )
    
    # Sources that will actually be queried (above threshold)
    sources_to_query: List[str] = Field(
        ..., 
        description="Sources that will be queried"
    )
    
    # Whether queries will run in parallel or sequential
    execution_mode: str = Field(
        default="parallel", 
        description="parallel or sequential execution"
    )
    
    # Reasoning for the plan
    plan_reasoning: str = Field(..., description="Why this plan was chosen")
    
    # Estimated time for execution
    estimated_time_ms: Optional[int] = Field(
        None, 
        description="Estimated execution time"
    )


class MultiSourceRequest(BaseModel):
    """
    Request model for multi-source agent queries.
    
    Allows users to query across multiple data sources with a single request.
    """
    # The natural language query
    query: str = Field(..., description="Natural language query")
    
    # Optional: Specify which sources to query (if not provided, auto-detect)
    sources: Optional[List[str]] = Field(
        None, 
        description="Specific sources to query (auto-detect if not provided)"
    )
    
    # Session ID for conversation context
    session_id: Optional[str] = Field(
        None, 
        description="Session ID for conversation history"
    )
    
    # Minimum confidence threshold for auto-detected sources
    confidence_threshold: float = Field(
        default=0.5, 
        ge=0.0, 
        le=1.0,
        description="Minimum confidence for auto-detected sources"
    )
    
    # Maximum number of sources to query
    max_sources: int = Field(
        default=3, 
        ge=1, 
        le=5,
        description="Maximum sources to query simultaneously"
    )
    
    # Whether to include the execution plan in response
    include_plan: bool = Field(
        default=True, 
        description="Include execution plan in response"
    )


class MultiSourceResponse(BaseModel):
    """
    Response model for multi-source agent queries.
    
    Contains the synthesized response along with individual source results.
    """
    # Synthesized natural language response combining all sources
    response: str = Field(..., description="Synthesized response")
    
    # Session ID for follow-up queries
    session_id: str = Field(..., description="Session ID")
    
    # Status of the overall query
    status: AgentTaskStatus = Field(..., description="Overall task status")
    
    # The execution plan that was followed
    plan: Optional[AgentPlan] = Field(None, description="Execution plan")
    
    # Individual results from each source
    source_results: List[SourceQueryResult] = Field(
        default_factory=list, 
        description="Results from each source"
    )
    
    # Sources that were successfully queried
    successful_sources: List[str] = Field(
        default_factory=list, 
        description="Sources that succeeded"
    )
    
    # Sources that failed
    failed_sources: List[str] = Field(
        default_factory=list, 
        description="Sources that failed"
    )
    
    # Total execution time in milliseconds
    total_execution_time_ms: Optional[float] = Field(
        None, 
        description="Total execution time"
    )
    
    # Timestamp
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, 
        description="Response timestamp"
    )


class AgentStreamEvent(BaseModel):
    """
    Event model for streaming multi-source query progress.
    
    Allows real-time updates to the frontend during execution.
    """
    # Event type
    event_type: str = Field(
        ..., 
        description="Event type: planning, source_start, source_complete, synthesizing, done, error"
    )
    
    # Relevant data for this event
    data: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Event-specific data"
    )
    
    # Optional message
    message: Optional[str] = Field(None, description="Human-readable message")
    
    # Timestamp
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, 
        description="Event timestamp"
    )







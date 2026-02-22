"""
Agent Orchestration Service for Multi-Source Queries.

This is the main orchestrator that coordinates queries across multiple data sources.
It handles the complete lifecycle of a multi-source query:
1. Planning - Determine which sources to query
2. Execution - Query sources in parallel
3. Synthesis - Combine results into unified response

The agent uses an intelligent planning approach with:
- Automatic source detection based on query content
- Parallel execution for speed
- Graceful handling of partial failures
- Streaming support for real-time feedback
"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_session_id
from app.services.mcp_service import mcp_service
from app.services.source_detector import source_detector
from app.services.result_synthesizer import result_synthesizer
from app.services.chat_service import chat_service
from app.models.agent import (
    MultiSourceRequest,
    MultiSourceResponse,
    AgentPlan,
    AgentTaskStatus,
    SourceQueryResult,
    DataSourceRelevance,
    AgentStreamEvent,
)

# Configure logging
logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates multi-source queries across data connectors.
    
    This is the central component of the agent system, responsible for:
    - Query planning and source detection
    - Parallel query execution
    - Result aggregation and synthesis
    - Error handling and partial failure recovery
    
    Architecture:
    ```
    User Query
        │
        ▼
    ┌─────────────────┐
    │  Source Detector │  ← Determines relevant sources
    └─────────────────┘
        │
        ▼
    ┌─────────────────┐
    │  Execution Plan  │  ← Creates execution strategy
    └─────────────────┘
        │
        ▼
    ┌─────────────────────────────────────┐
    │      Parallel Query Execution        │
    │  ┌─────┐  ┌─────┐  ┌─────┐         │
    │  │ S3  │  │JIRA │  │MySQL│  ...    │
    │  └─────┘  └─────┘  └─────┘         │
    └─────────────────────────────────────┘
        │
        ▼
    ┌─────────────────┐
    │Result Synthesizer│  ← Combines all results
    └─────────────────┘
        │
        ▼
    Unified Response
    ```
    """

    def __init__(self):
        """Initialize the agent orchestrator."""
        # Session storage for multi-turn conversations
        self.sessions: Dict[str, List[dict]] = {}
        
        # Default configuration
        self.default_confidence_threshold = 0.5
        self.default_max_sources = 3
        self.query_timeout_seconds = 60

    async def process_multi_source_query(
        self,
        request: MultiSourceRequest,
        user_id: Optional[str] = None,
        credential_session_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> MultiSourceResponse:
        """
        Process a multi-source query and return synthesized results.
        
        This is the main entry point for multi-source queries.
        
        Args:
            request: The multi-source query request
            user_id: Optional user ID for authenticated users
            credential_session_id: Optional session ID for credentials
            db: Optional database session
            
        Returns:
            MultiSourceResponse with synthesized results
        """
        start_time = time.time()
        session_id = request.session_id or generate_session_id()
        
        logger.info(f"🤖 Processing multi-source query: {request.query[:100]}...")
        
        try:
            # PHASE 1: PLANNING
            # Determine which sources to query
            plan = await self._create_execution_plan(request)
            
            if not plan.sources_to_query:
                # No relevant sources found
                return MultiSourceResponse(
                    response="I couldn't identify which data sources would be helpful for your query. "
                             "Please try being more specific about what data you're looking for.",
                    session_id=session_id,
                    status=AgentTaskStatus.FAILED,
                    plan=plan if request.include_plan else None,
                    total_execution_time_ms=(time.time() - start_time) * 1000,
                )
            
            logger.info(f"📋 Execution plan: {plan.sources_to_query}")
            
            # PHASE 2: EXECUTION
            # Query all sources in parallel
            source_results = await self._execute_queries_parallel(
                query=request.query,
                sources=plan.sources_to_query,
                plan=plan,
                user_id=user_id,
                credential_session_id=credential_session_id,
                db=db,
            )
            
            # Categorize results
            successful_sources = [r.datasource for r in source_results if r.success]
            failed_sources = [r.datasource for r in source_results if not r.success]
            
            # Determine overall status
            if not successful_sources:
                status = AgentTaskStatus.FAILED
            elif failed_sources:
                status = AgentTaskStatus.PARTIAL
            else:
                status = AgentTaskStatus.COMPLETED
            
            # PHASE 3: SYNTHESIS
            # Combine results into unified response
            synthesized_response = await result_synthesizer.synthesize(
                query=request.query,
                results=source_results,
                plan=plan,
            )
            
            total_time = (time.time() - start_time) * 1000
            logger.info(f"✅ Multi-source query completed in {total_time:.0f}ms "
                       f"({len(successful_sources)} succeeded, {len(failed_sources)} failed)")
            
            return MultiSourceResponse(
                response=synthesized_response,
                session_id=session_id,
                status=status,
                plan=plan if request.include_plan else None,
                source_results=source_results,
                successful_sources=successful_sources,
                failed_sources=failed_sources,
                total_execution_time_ms=total_time,
            )
            
        except asyncio.TimeoutError:
            logger.error("Multi-source query timed out", exc_info=True)
            return MultiSourceResponse(
                response="The query took too long to complete. Please try a simpler query.",
                session_id=session_id,
                status=AgentTaskStatus.FAILED,
                total_execution_time_ms=(time.time() - start_time) * 1000,
            )
        except (ConnectionError, OSError) as e:
            logger.error(f"Multi-source query connection error: {e}", exc_info=True)
            return MultiSourceResponse(
                response=f"Connection error while processing your query: {str(e)}",
                session_id=session_id,
                status=AgentTaskStatus.FAILED,
                total_execution_time_ms=(time.time() - start_time) * 1000,
            )
        except ValueError as e:
            logger.error(f"Multi-source query validation error: {e}", exc_info=True)
            return MultiSourceResponse(
                response=f"Invalid query parameters: {str(e)}",
                session_id=session_id,
                status=AgentTaskStatus.FAILED,
                total_execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def process_multi_source_query_stream(
        self,
        request: MultiSourceRequest,
        user_id: Optional[str] = None,
        credential_session_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """
        Process a multi-source query with streaming progress updates.
        
        Yields events as the query progresses through planning, execution,
        and synthesis phases. Enables real-time UI updates.
        
        Args:
            request: The multi-source query request
            user_id: Optional user ID
            credential_session_id: Optional session ID for credentials
            db: Optional database session
            
        Yields:
            AgentStreamEvent objects with progress updates
        """
        start_time = time.time()
        session_id = request.session_id or generate_session_id()
        
        logger.info(f"🤖 Streaming multi-source query: {request.query[:100]}...")
        
        # Emit: Query started
        yield AgentStreamEvent(
            event_type="started",
            data={"session_id": session_id, "query": request.query},
            message="🔍 Analyzing your query...",
        )
        
        try:
            # PHASE 1: PLANNING
            yield AgentStreamEvent(
                event_type="planning",
                data={},
                message="📋 Creating execution plan...",
            )
            
            plan = await self._create_execution_plan(request)
            
            yield AgentStreamEvent(
                event_type="plan_complete",
                data={
                    "sources": plan.sources_to_query,
                    "reasoning": plan.plan_reasoning,
                },
                message=f"📊 Will query: {', '.join(plan.sources_to_query)}",
            )
            
            if not plan.sources_to_query:
                yield AgentStreamEvent(
                    event_type="error",
                    data={"error": "No relevant sources identified"},
                    message="❌ Couldn't identify relevant data sources",
                )
                return
            
            # PHASE 2: EXECUTION
            yield AgentStreamEvent(
                event_type="executing",
                data={"sources": plan.sources_to_query},
                message="⚡ Querying data sources...",
            )
            
            # Execute queries and emit progress for each
            source_results = []
            
            # Create tasks for parallel execution
            tasks = []
            for source in plan.sources_to_query:
                # Get suggested approach from plan
                suggested = None
                for rel in plan.relevant_sources:
                    if rel.datasource == source:
                        suggested = rel.suggested_approach
                        break
                
                task = asyncio.create_task(
                    self._execute_single_query(
                        query=request.query,
                        datasource=source,
                        suggested_approach=suggested,
                        user_id=user_id,
                        credential_session_id=credential_session_id,
                        db=db,
                    )
                )
                tasks.append((source, task))
            
            # Wait for all tasks and emit events as they complete
            for source, task in tasks:
                yield AgentStreamEvent(
                    event_type="source_start",
                    data={"datasource": source},
                    message=f"🔄 Querying {source.upper()}...",
                )
                
                try:
                    result = await asyncio.wait_for(
                        task,
                        timeout=self.query_timeout_seconds
                    )
                    source_results.append(result)
                    
                    if result.success:
                        yield AgentStreamEvent(
                            event_type="source_complete",
                            data={
                                "datasource": source,
                                "success": True,
                                "tools_called": result.tools_called,
                            },
                            message=f"✅ {source.upper()} query complete",
                        )
                    else:
                        yield AgentStreamEvent(
                            event_type="source_complete",
                            data={
                                "datasource": source,
                                "success": False,
                                "error": result.error,
                            },
                            message=f"⚠️ {source.upper()} query failed",
                        )
                        
                except asyncio.TimeoutError:
                    source_results.append(SourceQueryResult(
                        datasource=source,
                        success=False,
                        error="Query timed out",
                    ))
                    yield AgentStreamEvent(
                        event_type="source_complete",
                        data={"datasource": source, "success": False, "error": "Timeout"},
                        message=f"⏱️ {source.upper()} query timed out",
                    )
            
            # PHASE 3: SYNTHESIS
            yield AgentStreamEvent(
                event_type="synthesizing",
                data={},
                message="🧠 Synthesizing results...",
            )
            
            # Stream the synthesis
            synthesis_chunks = []
            async for chunk in result_synthesizer.synthesize_stream(
                query=request.query,
                results=source_results,
                plan=plan,
            ):
                synthesis_chunks.append(chunk)
                yield AgentStreamEvent(
                    event_type="synthesis_chunk",
                    data={"content": chunk},
                    message=None,
                )
            
            # Emit completion
            successful_sources = [r.datasource for r in source_results if r.success]
            failed_sources = [r.datasource for r in source_results if not r.success]
            
            total_time = (time.time() - start_time) * 1000
            
            yield AgentStreamEvent(
                event_type="done",
                data={
                    "session_id": session_id,
                    "successful_sources": successful_sources,
                    "failed_sources": failed_sources,
                    "total_time_ms": total_time,
                },
                message=f"✨ Query completed in {total_time/1000:.1f}s",
            )
            
        except asyncio.TimeoutError:
            logger.error("Streaming query timed out", exc_info=True)
            yield AgentStreamEvent(
                event_type="error",
                data={"error": "Query timed out"},
                message="❌ Query timed out",
            )
        except (ConnectionError, OSError) as e:
            logger.error(f"Streaming query connection error: {e}", exc_info=True)
            yield AgentStreamEvent(
                event_type="error",
                data={"error": str(e)},
                message=f"❌ Connection error: {str(e)}",
            )
        except ValueError as e:
            logger.error(f"Streaming query validation error: {e}", exc_info=True)
            yield AgentStreamEvent(
                event_type="error",
                data={"error": str(e)},
                message=f"❌ Invalid query: {str(e)}",
            )

    async def _create_execution_plan(
        self,
        request: MultiSourceRequest
    ) -> AgentPlan:
        """
        Create an execution plan for the multi-source query.
        
        Determines which sources to query based on:
        1. Explicitly specified sources (if provided)
        2. Auto-detected sources based on query content
        
        Args:
            request: The multi-source request
            
        Returns:
            AgentPlan with sources to query and reasoning
        """
        # Get all available sources
        available_sources = [ds["id"] for ds in mcp_service.get_available_datasources()]
        
        if request.sources:
            # Use explicitly specified sources
            valid_sources = [s for s in request.sources if s in available_sources]
            
            if not valid_sources:
                return AgentPlan(
                    original_query=request.query,
                    relevant_sources=[],
                    sources_to_query=[],
                    execution_mode="parallel",
                    plan_reasoning="No valid sources specified",
                )
            
            # Create relevance entries for specified sources
            relevant_sources = [
                DataSourceRelevance(
                    datasource=s,
                    confidence=1.0,
                    reasoning="Explicitly specified by user",
                    suggested_approach=None,
                )
                for s in valid_sources
            ]
            
            return AgentPlan(
                original_query=request.query,
                relevant_sources=relevant_sources,
                sources_to_query=valid_sources[:request.max_sources],
                execution_mode="parallel",
                plan_reasoning=f"Using user-specified sources: {', '.join(valid_sources)}",
            )
        
        # Auto-detect relevant sources
        detected_sources = await source_detector.detect_sources(
            query=request.query,
            available_sources=available_sources,
        )
        
        if not detected_sources:
            return AgentPlan(
                original_query=request.query,
                relevant_sources=[],
                sources_to_query=[],
                execution_mode="parallel",
                plan_reasoning="No relevant sources detected for this query",
            )
        
        # Filter by confidence threshold
        qualified_sources = [
            s for s in detected_sources
            if s.confidence >= request.confidence_threshold
        ]
        
        # Limit to max_sources
        sources_to_query = [s.datasource for s in qualified_sources[:request.max_sources]]
        
        # Build reasoning
        reasoning_parts = []
        for s in qualified_sources[:request.max_sources]:
            reasoning_parts.append(f"{s.datasource} ({s.confidence:.0%}): {s.reasoning}")
        
        return AgentPlan(
            original_query=request.query,
            relevant_sources=detected_sources,
            sources_to_query=sources_to_query,
            execution_mode="parallel",
            plan_reasoning="; ".join(reasoning_parts) if reasoning_parts else "Using detected sources",
            estimated_time_ms=len(sources_to_query) * 2000,  # Rough estimate
        )

    async def _execute_queries_parallel(
        self,
        query: str,
        sources: List[str],
        plan: AgentPlan,
        user_id: Optional[str] = None,
        credential_session_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[SourceQueryResult]:
        """
        Execute queries across multiple sources in parallel.
        
        Uses asyncio.gather for concurrent execution with proper
        error handling for individual source failures.
        
        Args:
            query: The user query
            sources: List of sources to query
            plan: The execution plan
            user_id: Optional user ID
            credential_session_id: Optional session ID
            db: Optional database session
            
        Returns:
            List of SourceQueryResult from all sources
        """
        # Create tasks for each source
        tasks = []
        for source in sources:
            # Get suggested approach from plan
            suggested_approach = None
            for rel in plan.relevant_sources:
                if rel.datasource == source:
                    suggested_approach = rel.suggested_approach
                    break
            
            task = self._execute_single_query(
                query=query,
                datasource=source,
                suggested_approach=suggested_approach,
                user_id=user_id,
                credential_session_id=credential_session_id,
                db=db,
            )
            tasks.append(task)
        
        # Execute all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(SourceQueryResult(
                    datasource=sources[i],
                    success=False,
                    error=str(result),
                ))
            else:
                final_results.append(result)
        
        return final_results

    async def _execute_single_query(
        self,
        query: str,
        datasource: str,
        suggested_approach: Optional[str] = None,
        user_id: Optional[str] = None,
        credential_session_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> SourceQueryResult:
        """
        Execute a query against a single data source.
        
        Uses the chat_service to leverage its tool-calling capabilities
        and parameter injection logic.
        
        Args:
            query: The user query
            datasource: The data source to query
            suggested_approach: Optional hint for query approach
            user_id: Optional user ID
            credential_session_id: Optional session ID
            db: Optional database session
            
        Returns:
            SourceQueryResult with query results
        """
        start_time = time.time()
        
        logger.info(f"Executing query on {datasource}: {query[:50]}...")
        
        try:
            # Create a temporary session for this query
            temp_session_id = generate_session_id(prefix=f"agent_{datasource}_")
            
            # Use the existing chat service for query execution
            # This leverages all the tool-calling and parameter injection logic
            response_text, tool_calls = await chat_service.process_message(
                message=query,
                datasource=datasource,
                session_id=temp_session_id,
                credential_session_id=credential_session_id,
                user_id=user_id,
                db=db,
            )
            
            execution_time = (time.time() - start_time) * 1000
            
            # Extract tools called
            tools_called = [tc.get("name", "unknown") for tc in (tool_calls or [])]
            
            return SourceQueryResult(
                datasource=datasource,
                success=True,
                data=response_text,
                summary=self._extract_summary(response_text),
                tools_called=tools_called,
                execution_time_ms=execution_time,
            )
            
        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Query to {datasource} timed out")

            return SourceQueryResult(
                datasource=datasource,
                success=False,
                error="Query timed out",
                execution_time_ms=execution_time,
            )
        except (ConnectionError, OSError) as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Query to {datasource} connection error: {e}")

            return SourceQueryResult(
                datasource=datasource,
                success=False,
                error=f"Connection error: {str(e)}",
                execution_time_ms=execution_time,
            )
        except ValueError as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Query to {datasource} validation error: {e}")

            return SourceQueryResult(
                datasource=datasource,
                success=False,
                error=f"Invalid parameters: {str(e)}",
                execution_time_ms=execution_time,
            )

    def _extract_summary(self, response: str, max_length: int = 200) -> str:
        """
        Extract a brief summary from a response.
        
        Takes the first meaningful sentence or portion.
        """
        if not response:
            return ""
        
        # Try to get first paragraph or sentence
        lines = response.strip().split('\n')
        first_line = ""
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('|'):
                first_line = line
                break
        
        if len(first_line) <= max_length:
            return first_line
        
        # Truncate at word boundary
        truncated = first_line[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.7:
            truncated = truncated[:last_space]
        
        return truncated + "..."

    async def detect_if_multi_source(self, query: str) -> bool:
        """
        Quickly detect if a query should use multi-source processing.
        
        Helper method to determine whether to route to multi-source
        or single-source processing.
        
        Args:
            query: The user query
            
        Returns:
            True if multi-source processing is recommended
        """
        return source_detector.is_multi_source_query(query)

    async def suggest_sources(
        self,
        query: str,
        max_suggestions: int = 5
    ) -> List[DataSourceRelevance]:
        """
        Suggest relevant sources for a query without executing it.
        
        Useful for UI previews or query planning.
        
        Args:
            query: The user query
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of DataSourceRelevance sorted by confidence
        """
        available_sources = [ds["id"] for ds in mcp_service.get_available_datasources()]
        
        suggestions = await source_detector.detect_sources(
            query=query,
            available_sources=available_sources,
        )
        
        return suggestions[:max_suggestions]


# Create global instance for import
agent_orchestrator = AgentOrchestrator()







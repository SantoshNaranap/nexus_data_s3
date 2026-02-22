"""
Chat service for handling LLM interactions.

This service orchestrates chat interactions by delegating to specialized services:
- chat_history_service: Message persistence and retrieval
- tool_routing_service: Intelligent tool selection
- prompt_service: System prompt generation
- claude_interaction_service: LLM API calls
- response_formatter: Response formatting for ultra-fast path
- parameter_extractor: Parameter extraction from context
"""

import logging
import asyncio
import time
import re
import json
from typing import List, Dict, Any, AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.mcp_service import mcp_service
from app.services.chat_history_service import chat_history_service
from app.services.tool_routing_service import tool_routing_service
from app.services.prompt_service import prompt_service
from app.services.claude_interaction_service import claude_interaction_service
from app.services.response_formatter import response_formatter

logger = logging.getLogger(__name__)

# Performance tracking
PERF_METRICS = {
    "ultra_fast_path_count": 0,
    "fast_path_count": 0,
    "standard_path_count": 0,
    "total_requests": 0,
}


class ChatService:
    """
    Service for handling chat interactions with Claude and MCP.

    This is a thin orchestration layer that delegates to specialized services:
    - Chat history: chat_history_service
    - Tool routing: tool_routing_service
    - System prompts: prompt_service
    - Claude API calls: claude_interaction_service
    - Response formatting: response_formatter
    """

    def __init__(self):
        # In-memory session storage for anonymous users
        self.sessions: Dict[str, List[dict]] = {}

    async def _get_session_messages(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        datasource: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """
        Get messages for a session.

        For authenticated users: Load from database via chat_history_service.
        For anonymous users: Load from in-memory storage.
        """
        if user_id and db and datasource:
            # Authenticated user - load from database
            messages = await chat_history_service.get_recent_messages(
                db=db,
                user_id=user_id,
                session_id=session_id,
            )
            # Filter out empty messages
            return [m for m in messages if m.get("content") and str(m.get("content", "")).strip()]
        else:
            # Anonymous user - use in-memory storage
            if session_id not in self.sessions:
                self.sessions[session_id] = []
            return self.sessions[session_id]

    async def _save_messages(
        self,
        user_id: str,
        session_id: str,
        datasource: str,
        messages: List[dict],
        db: AsyncSession,
    ) -> None:
        """Save messages to database for authenticated users."""
        try:
            for message in messages:
                content = message.get("content")
                # Skip empty messages
                if not content or not str(content).strip():
                    continue

                await chat_history_service.add_message(
                    db=db,
                    user_id=user_id,
                    session_id=session_id,
                    datasource=datasource,
                    role=message.get("role"),
                    content=content,
                )
        except Exception as e:
            logger.error(f"Failed to save chat history: {str(e)}")
            # Don't fail the request if saving fails

    async def process_message(
        self,
        message: str,
        datasource: str,
        session_id: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> tuple[str, List[dict]]:
        """Process a chat message using Claude and MCP tools."""
        PERF_METRICS["total_requests"] += 1

        # Get session history
        messages = await self._get_session_messages(
            session_id=session_id,
            user_id=user_id,
            datasource=datasource,
            db=db,
        )

        # Add user message to history
        user_message = {"role": "user", "content": message}
        messages.append(user_message)

        # Get available tools from MCP server
        tools = await mcp_service.get_cached_tools(datasource)

        # Create system prompt using prompt_service
        from app.connectors import get_connector
        connector = get_connector(datasource)
        connector_name = connector.metadata.name if connector else datasource
        system_prompt = prompt_service.get_system_prompt(datasource, connector_name)

        # TRY FAST PATH: Use tool_routing_service for routing
        fast_tools = await tool_routing_service.fast_route(message, tools, datasource)

        if fast_tools:
            # FAST PATH: Direct routing identified tools, execute in parallel
            PERF_METRICS["fast_path_count"] += 1
            logger.info(f"FAST PATH with {len(fast_tools)} tool(s): {[t['tool'] for t in fast_tools]}")

            # Execute tools in parallel
            tool_results = await self._execute_tools_parallel(
                fast_tools, datasource, credential_session_id, user_id, db
            )

            # Build context from tool results for Claude to generate response
            # Check for error responses and format them clearly
            tool_context_parts = []
            for r in tool_results:
                result_text = r.get('result', r.get('error', 'No result'))
                logger.info(f"Tool result for {r.get('tool')}: {result_text[:200] if result_text else 'EMPTY'}")
                # Detect JSON error responses and extract the error message
                if result_text and '"error"' in result_text:
                    try:
                        result_json = json.loads(result_text)
                        if 'error' in result_json:
                            error_msg = result_json['error']
                            suggestion = result_json.get('suggestion', '')
                            result_text = f"ERROR: {error_msg}"
                            if suggestion:
                                result_text += f"\nSuggestion: {suggestion}"
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep original text if not valid JSON
                tool_context_parts.append(f"Tool: {r['tool']}\nResult: {result_text}")
            tool_context = "\n\n".join(tool_context_parts)
            logger.info(f"Final tool_context: {tool_context[:500]}")

            # Add tool results to messages for context
            messages.append({
                "role": "assistant",
                "content": f"I retrieved the following data:\n{tool_context[:8000]}"
            })
            messages.append({
                "role": "user",
                "content": "Based on the data above, please provide a clear, well-formatted response to my original question. IMPORTANT: If the data shows no results, empty data, or errors, tell the user exactly that - do NOT make up or invent data."
            })

            logger.info(f"Sending to Claude with {len(messages)} messages")

            # Use Claude just for response generation (no tools needed)
            response_text, _ = await claude_interaction_service.call_claude(
                messages=messages,
                tools=[],  # No tools needed for response generation
                system_prompt=system_prompt,
                datasource=datasource,
                credential_session_id=credential_session_id,
                user_id=user_id,
                db=db,
            )
            logger.info(f"Claude response_text length: {len(response_text) if response_text else 0}")
            logger.info(f"Claude response_text: {response_text[:300] if response_text else 'EMPTY'}")
            tool_calls = [{"tool": t["tool"], "args": t["args"]} for t in fast_tools]
        else:
            # SLOW PATH: Process with Claude tool loop
            PERF_METRICS["standard_path_count"] += 1
            response_text, tool_calls = await claude_interaction_service.call_claude(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                datasource=datasource,
                credential_session_id=credential_session_id,
                user_id=user_id,
                db=db,
            )

        # Add assistant message to history
        assistant_message = {"role": "assistant", "content": response_text}
        messages.append(assistant_message)

        # Save to database if authenticated user
        if user_id and db:
            await self._save_messages(user_id, session_id, datasource, [user_message, assistant_message], db)

        return response_text, tool_calls

    async def process_message_stream(
        self,
        message: str,
        datasource: str,
        session_id: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[str, None]:
        """Process a chat message with streaming response - OPTIMIZED FOR SPEED."""
        start_time = time.time()
        PERF_METRICS["total_requests"] += 1

        # Check if user wants fresh data (bypass cache)
        force_refresh = mcp_service.should_force_refresh(message)
        if force_refresh:
            logger.info(f"User requested refresh - bypassing cache")

        # CHECK ULTRA-FAST PATH FIRST (skip Claude entirely for simple queries)
        if tool_routing_service.can_use_ultra_fast_path(message, datasource):
            logger.info(f"Attempting ULTRA-FAST PATH (no Claude API call)")

            # Get tool call directly
            direct_tools = tool_routing_service.direct_route(message, datasource)
            if direct_tools and len(direct_tools) == 1:
                tool_call = direct_tools[0]
                tool_name = tool_call["tool"]
                tool_args = tool_call.get("args", {})

                # Execute tool (email injection for Google Workspace happens in mcp_service)
                try:
                    result = await mcp_service.call_tool(
                        datasource=datasource,
                        tool_name=tool_name,
                        arguments=tool_args,
                        user_id=user_id,
                        session_id=credential_session_id if not user_id else None,
                        db=db,
                        force_refresh=force_refresh,
                    )

                    # Extract result text
                    result_text = ""
                    if result:
                        for content in result:
                            if hasattr(content, "text"):
                                result_text += content.text

                    # Try to format response without Claude
                    formatted = response_formatter.format_ultra_fast_response(datasource, tool_name, result_text)
                    if formatted:
                        PERF_METRICS["ultra_fast_path_count"] += 1
                        elapsed = time.time() - start_time
                        logger.info(f"ULTRA-FAST PATH success in {elapsed:.2f}s (no Claude!)")

                        # Stream the formatted response in word-sized chunks
                        words = re.findall(r'\S+\s*|\n+', formatted)
                        for word in words:
                            yield {"type": "text", "content": word}

                        # Save to history
                        messages = await self._get_session_messages(session_id, user_id, datasource, db)
                        user_message = {"role": "user", "content": message}
                        assistant_message = {"role": "assistant", "content": formatted}
                        messages.append(user_message)
                        messages.append(assistant_message)

                        if user_id and db:
                            await self._save_messages(user_id, session_id, datasource, [user_message, assistant_message], db)

                        return  # Exit early - we're done!

                except Exception as e:
                    logger.warning(f"Ultra-fast path failed, falling back to regular path: {e}")

        # IMMEDIATE FEEDBACK - Send within 50ms
        immediate_feedback = response_formatter.get_immediate_feedback_message(datasource, message)
        thinking_summary = self._get_thinking_summary(datasource, message)
        yield {"type": "thinking", "content": thinking_summary}
        yield {"type": "text", "content": immediate_feedback + "\n\n"}
        logger.info(f"Immediate feedback sent in {(time.time() - start_time)*1000:.0f}ms")

        # Get session history
        messages = await self._get_session_messages(
            session_id=session_id,
            user_id=user_id,
            datasource=datasource,
            db=db,
        )

        # Add user message to history
        user_message = {"role": "user", "content": message}
        messages.append(user_message)

        # Get available tools from MCP server (with caching)
        tools = await mcp_service.get_cached_tools(datasource)

        # Create system prompt using prompt_service
        from app.connectors import get_connector
        connector = get_connector(datasource)
        connector_name = connector.metadata.name if connector else datasource
        system_prompt = prompt_service.get_system_prompt(datasource, connector_name)

        # TRY FAST PATH: Use tool_routing_service for routing
        fast_tools = await tool_routing_service.fast_route(message, tools, datasource)

        if fast_tools:
            # FAST PATH: Routing identified tools, execute in parallel
            PERF_METRICS["fast_path_count"] += 1
            logger.info(f"Using FAST PATH with {len(fast_tools)} tool(s)")
            yield "Found relevant data...\n\n"

            # Execute tools in parallel
            tool_results = await self._execute_tools_parallel(
                fast_tools, datasource, credential_session_id, user_id, db
            )

            # Build context from tool results
            # Check for error responses and format them clearly
            tool_context_parts = []
            for r in tool_results:
                result_text = r.get('result', r.get('error', 'No result'))
                # Detect JSON error responses and extract the error message
                if result_text and '"error"' in result_text:
                    try:
                        result_json = json.loads(result_text)
                        if 'error' in result_json:
                            error_msg = result_json['error']
                            suggestion = result_json.get('suggestion', '')
                            result_text = f"ERROR: {error_msg}"
                            if suggestion:
                                result_text += f"\nSuggestion: {suggestion}"
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep original text if not valid JSON
                tool_context_parts.append(f"Tool: {r['tool']}\nResult: {result_text}")
            tool_context = "\n\n".join(tool_context_parts)

            # Add tool results to messages for context
            messages.append({
                "role": "assistant",
                "content": f"I retrieved the following data:\n{tool_context[:8000]}"
            })
            messages.append({
                "role": "user",
                "content": "Based on the data above, please provide a clear, well-formatted response to my original question. IMPORTANT: If the data shows no results, empty data, or errors, tell the user exactly that - do NOT make up or invent data."
            })

            # Use Claude for response generation via claude_interaction_service
            full_response = ""
            async for event in claude_interaction_service.call_claude_stream(
                messages=messages,
                tools=[],  # No tools needed for response generation
                system_prompt=system_prompt,
                datasource=datasource,
                credential_session_id=credential_session_id,
                user_id=user_id,
                db=db,
            ):
                if isinstance(event, dict):
                    if event.get("type") == "text":
                        full_response += event.get("content", "")
                    yield event
                else:
                    full_response += str(event)
                    yield event

            logger.info(f"FAST PATH total time: {time.time() - start_time:.2f}s")

        else:
            # STANDARD PATH: Complex query, use full flow via claude_interaction_service
            PERF_METRICS["standard_path_count"] += 1
            logger.info(f"Using STANDARD PATH (complex query)")
            yield {"type": "thinking", "content": "Analyzing your request..."}

            full_response = ""
            async for event in claude_interaction_service.call_claude_stream(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                datasource=datasource,
                credential_session_id=credential_session_id,
                user_id=user_id,
                db=db,
            ):
                if isinstance(event, dict):
                    if event.get("type") == "text":
                        full_response += event.get("content", "")
                    yield event
                else:
                    full_response += str(event)
                    yield event

            logger.info(f"STANDARD PATH total time: {time.time() - start_time:.2f}s")

        # Add assistant message to history
        assistant_message = {"role": "assistant", "content": full_response}
        messages.append(assistant_message)

        # Save to database if authenticated user
        if user_id and db:
            await self._save_messages(user_id, session_id, datasource, [user_message, assistant_message], db)

    async def _execute_tools_parallel(
        self,
        tool_calls: List[dict],
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """Execute multiple tool calls in parallel for speed."""
        start_time = time.time()

        async def execute_single_tool(tool_call: dict) -> dict:
            tool_name = tool_call.get("tool") or tool_call.get("name")
            arguments = tool_call.get("args") or tool_call.get("arguments", {})

            try:
                result = await mcp_service.call_tool(
                    datasource=datasource,
                    tool_name=tool_name,
                    arguments=arguments,
                    user_id=user_id,
                    session_id=credential_session_id if not user_id else None,
                    db=db,
                )

                result_text = ""
                if result:
                    for content in result:
                        if hasattr(content, "text"):
                            result_text += content.text

                return {
                    "tool": tool_name,
                    "success": True,
                    "result": result_text,
                }
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                return {
                    "tool": tool_name,
                    "success": False,
                    "error": str(e),
                }

        # Execute all tools in parallel
        results = await asyncio.gather(
            *[execute_single_tool(tc) for tc in tool_calls],
            return_exceptions=True
        )

        elapsed = time.time() - start_time
        logger.info(f"Parallel tool execution completed in {elapsed:.2f}s ({len(tool_calls)} tools)")

        # Convert exceptions to error results
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({
                    "tool": tool_calls[i].get("tool", "unknown"),
                    "success": False,
                    "error": str(r),
                })
            else:
                final_results.append(r)

        return final_results

    def _get_thinking_summary(self, datasource: str, message: str) -> str:
        """Generate a thinking summary for the collapsible thinking indicator."""
        message_lower = message.lower()

        # Add datasource context
        datasource_names = {
            "s3": "Amazon S3",
            "jira": "JIRA",
            "mysql": "MySQL database",
            "google_workspace": "Google Workspace",
            "slack": "Slack",
            "shopify": "Shopify",
            "github": "GitHub",
        }
        ds_name = datasource_names.get(datasource, datasource)

        # Analyze query intent
        if any(kw in message_lower for kw in ["search", "find", "look for", "where"]):
            return f"Searching {ds_name} for relevant information"
        elif any(kw in message_lower for kw in ["list", "show", "get", "what"]):
            return f"Retrieving data from {ds_name}"
        elif any(kw in message_lower for kw in ["compare", "difference", "between"]):
            return f"Comparing information in {ds_name}"
        else:
            return f"Querying {ds_name}"

    # Legacy methods for backwards compatibility
    async def save_chat_history(
        self,
        user_id: str,
        session_id: str,
        datasource: str,
        messages: List[dict],
        db: AsyncSession,
    ) -> None:
        """Legacy method - delegates to _save_messages."""
        await self._save_messages(user_id, session_id, datasource, messages, db)

    async def get_chat_history(
        self,
        user_id: str,
        datasource: str,
        session_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """Legacy method - delegates to chat_history_service."""
        if not db:
            return []
        return await chat_history_service.get_recent_messages(
            db=db,
            user_id=user_id,
            session_id=session_id or "",
        )

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        total = PERF_METRICS["total_requests"] or 1
        return {
            "total_requests": PERF_METRICS["total_requests"],
            "ultra_fast_path_count": PERF_METRICS["ultra_fast_path_count"],
            "fast_path_count": PERF_METRICS["fast_path_count"],
            "standard_path_count": PERF_METRICS["standard_path_count"],
            "ultra_fast_path_pct": PERF_METRICS["ultra_fast_path_count"] / total * 100,
            "fast_path_pct": PERF_METRICS["fast_path_count"] / total * 100,
            "standard_path_pct": PERF_METRICS["standard_path_count"] / total * 100,
        }


# Global chat service instance
chat_service = ChatService()

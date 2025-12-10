"""
Claude Interaction Service - Handles all LLM API calls.

This service encapsulates all interactions with the Claude API, including:
1. Standard message processing with tool support
2. Streaming message processing with extended thinking
3. Parallel tool execution

Separating this from the chat service allows for:
1. Cleaner code - LLM interaction logic is isolated
2. Easier testing - can mock Claude responses
3. Better monitoring - centralized place for API metrics
"""

import logging
import asyncio
import time
import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from concurrent.futures import ThreadPoolExecutor

from anthropic.types import ToolUseBlock, TextBlock

from app.services.claude_client import claude_client, get_quirky_thinking_message
from app.services.mcp_service import mcp_service
from app.services.parameter_injection_service import parameter_injection_service

logger = logging.getLogger(__name__)

# Thread pool for running synchronous streaming in background
_executor = ThreadPoolExecutor(max_workers=10)

# Performance tracking
LLM_METRICS = {
    "sonnet_generation_time": [],
    "tool_execution_time": [],
    "total_tool_calls": 0,
}


class ClaudeInteractionService:
    """
    Handles all Claude API interactions with tool support.

    Provides both synchronous and streaming interfaces for chat completions,
    with automatic tool execution and parameter injection.
    """

    def __init__(self):
        self.client = claude_client.client
        self.max_iterations = 10  # Reduced from 25 to prevent endless retry loops
        self.max_consecutive_errors = 3  # Stop after 3 consecutive errors

    async def call_claude(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Call Claude API with tool support (non-streaming).

        Args:
            messages: Conversation history
            tools: Available tools
            system_prompt: System prompt
            datasource: Active datasource
            credential_session_id: Session ID for credentials
            user_id: User ID for credentials
            db: Database session

        Returns:
            Tuple of (response_text, tool_calls_made)
        """
        tool_calls_made = []

        for iteration in range(self.max_iterations):
            # Call Claude
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None,
            )

            # Check if Claude wants to use tools
            tool_use_blocks = [
                block for block in response.content if isinstance(block, ToolUseBlock)
            ]

            if not tool_use_blocks:
                # No more tool calls, extract text response
                text_blocks = [
                    block for block in response.content if isinstance(block, TextBlock)
                ]
                response_text = "\n".join(block.text for block in text_blocks)
                return response_text, tool_calls_made

            # Execute tool calls
            tool_results = await self._execute_tool_calls(
                tool_use_blocks=tool_use_blocks,
                datasource=datasource,
                messages=messages,
                credential_session_id=credential_session_id,
                user_id=user_id,
                db=db,
                tool_calls_made=tool_calls_made,
            )

            # Add tool results to messages
            messages.append({
                "role": "assistant",
                "content": response.content,
            })
            messages.append({
                "role": "user",
                "content": tool_results,
            })

        # Max iterations reached
        return "I apologize, but I encountered an issue processing your request. Please try rephrasing your question.", tool_calls_made

    async def call_claude_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Call Claude API with streaming and tool support - TRUE ASYNC STREAMING.

        Now yields structured events for better frontend handling:
        - {"type": "thinking", "content": "..."} - Thinking/reasoning updates
        - {"type": "text", "content": "..."} - Actual response text
        - {"type": "tool_start", "tool": "...", "description": "..."} - Tool execution starting
        - {"type": "tool_end", "tool": "...", "success": bool} - Tool execution complete

        Args:
            messages: Conversation history
            tools: Available tools
            system_prompt: System prompt
            datasource: Active datasource
            credential_session_id: Session ID for credentials
            user_id: User ID for credentials
            db: Database session

        Yields:
            Structured event dictionaries
        """
        consecutive_errors = 0
        last_failed_query = None
        stream_start = time.time()

        for iteration in range(self.max_iterations):
            # Check if we've hit too many consecutive errors
            if consecutive_errors >= self.max_consecutive_errors:
                logger.warning(f"Stopping after {consecutive_errors} consecutive errors")
                yield {"type": "text", "content": "\n\nI'm having trouble executing this query. Please try rephrasing your request."}
                return

            # Use an async queue to bridge sync streaming to async
            queue: asyncio.Queue = asyncio.Queue()
            tool_use_blocks_holder = []
            final_message_holder = [None]

            def run_stream():
                """Run the synchronous stream in a thread."""
                try:
                    stream = self.client.messages.stream(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=16000,
                        system=system_prompt,
                        messages=messages,
                        tools=tools if tools else None,
                    )

                    first_token = True
                    with stream as event_stream:
                        for event in event_stream:
                            if event.type == "content_block_delta":
                                if hasattr(event.delta, "text"):
                                    if first_token:
                                        ttft = (time.time() - stream_start) * 1000
                                        logger.info(f"⚡ Time to first token: {ttft:.0f}ms")
                                        first_token = False
                                    queue.put_nowait({"type": "text", "content": event.delta.text})
                            elif event.type == "content_block_start":
                                if hasattr(event.content_block, "type"):
                                    if event.content_block.type == "tool_use":
                                        tool_use_blocks_holder.append(event.content_block)
                                        # Immediately signal tool detection
                                        queue.put_nowait({
                                            "type": "thinking",
                                            "content": f"I'll query {datasource} to get the information you need..."
                                        })

                        # Get final message
                        final_message_holder[0] = event_stream.get_final_message()

                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    queue.put_nowait({"type": "error", "content": str(e)})
                finally:
                    queue.put_nowait(None)  # Signal end

            # Start streaming in background thread
            loop = asyncio.get_event_loop()
            stream_task = loop.run_in_executor(_executor, run_stream)

            # Yield events as they come from the queue
            while True:
                try:
                    # Use asyncio.wait_for to check queue with timeout, allowing other tasks
                    event = await asyncio.wait_for(queue.get(), timeout=0.05)
                    if event is None:
                        break
                    yield event
                except asyncio.TimeoutError:
                    # No event yet, let other tasks run
                    await asyncio.sleep(0.01)
                    continue

            # Wait for stream to complete
            await stream_task

            # Get final message and check for tool use
            final_message = final_message_holder[0]
            tool_use_blocks = tool_use_blocks_holder

            if not tool_use_blocks and final_message:
                tool_use_blocks = [
                    block for block in final_message.content
                    if isinstance(block, ToolUseBlock)
                ]

            if not tool_use_blocks:
                # No tool calls, we're done
                return

            # Execute tool calls with streaming feedback
            tool_results = []
            for tool_use in tool_use_blocks:
                # Inject missing parameters
                tool_use.input = parameter_injection_service.inject_parameters(
                    tool_name=tool_use.name,
                    tool_input=tool_use.input,
                    datasource=datasource,
                    messages=messages,
                )

                # Show tool execution starting
                tool_description = get_quirky_thinking_message(tool_use.name)
                yield {
                    "type": "tool_start",
                    "tool": tool_use.name,
                    "description": tool_description.strip(" []✓✗\n")
                }

                tool_start = time.time()
                logger.info(f"🔧 Calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
                    # Call the MCP tool
                    result = await mcp_service.call_tool(
                        datasource=datasource,
                        tool_name=tool_use.name,
                        arguments=tool_use.input,
                        user_id=user_id,
                        session_id=credential_session_id if not user_id else None,
                        db=db,
                    )

                    result_text = ""
                    if result:
                        for content in result:
                            if hasattr(content, "text"):
                                result_text += content.text

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    })

                    tool_elapsed = (time.time() - tool_start) * 1000
                    logger.info(f"✅ Tool {tool_use.name} completed in {tool_elapsed:.0f}ms")
                    LLM_METRICS["total_tool_calls"] += 1

                    # Auto-cache describe_table results
                    if tool_use.name == "describe_table" and result_text:
                        table_name = tool_use.input.get("table", "")
                        if table_name:
                            mcp_service.cache_schema(table_name, result_text)

                    # Check for errors in result
                    is_error = "Unknown column" in result_text or "Access denied" in result_text or "Error" in result_text[:50]
                    if is_error:
                        consecutive_errors += 1
                        current_query = str(tool_use.input)
                        if current_query == last_failed_query:
                            consecutive_errors += 1
                        last_failed_query = current_query
                    else:
                        consecutive_errors = 0
                        last_failed_query = None

                    yield {
                        "type": "tool_end",
                        "tool": tool_use.name,
                        "success": not is_error,
                        "duration_ms": tool_elapsed
                    }

                except asyncio.TimeoutError:
                    logger.error(f"Tool call {tool_use.name} timed out")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": "Error: Tool execution timed out",
                        "is_error": True,
                    })
                    consecutive_errors += 1
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": "Timed out"}
                except (ConnectionError, OSError) as e:
                    logger.error(f"Tool call {tool_use.name} connection error: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: Connection failed - {str(e)}",
                        "is_error": True,
                    })
                    consecutive_errors += 1
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": "Connection error"}
                except ValueError as e:
                    logger.error(f"Tool call {tool_use.name} validation error: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: Invalid parameters - {str(e)}",
                        "is_error": True,
                    })
                    consecutive_errors += 1
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": "Invalid parameters"}

            # Yield thinking update before next iteration
            yield {"type": "thinking", "content": "Analyzing the results..."}

            # Add tool results to messages and continue
            messages.append({
                "role": "assistant",
                "content": final_message.content,
            })
            messages.append({
                "role": "user",
                "content": tool_results,
            })

            # Reset stream start for next iteration
            stream_start = time.time()

        # Max iterations reached
        yield {"type": "text", "content": "\n\nI apologize, but I encountered an issue processing your request. Please try rephrasing your question."}

    async def _execute_tool_calls(
        self,
        tool_use_blocks: List[ToolUseBlock],
        datasource: str,
        messages: List[Dict[str, Any]],
        credential_session_id: Optional[str],
        user_id: Optional[str],
        db: Optional[Any],
        tool_calls_made: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Execute a list of tool calls.

        Args:
            tool_use_blocks: Tool use blocks from Claude
            datasource: Active datasource
            messages: Conversation history for parameter extraction
            credential_session_id: Session ID for credentials
            user_id: User ID for credentials
            db: Database session
            tool_calls_made: List to append executed tool calls

        Returns:
            List of tool results
        """
        tool_results = []

        for tool_use in tool_use_blocks:
            # Inject missing parameters
            tool_use.input = parameter_injection_service.inject_parameters(
                tool_name=tool_use.name,
                tool_input=tool_use.input,
                datasource=datasource,
                messages=messages,
            )

            logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

            try:
                # Call the MCP tool
                result = await mcp_service.call_tool(
                    datasource=datasource,
                    tool_name=tool_use.name,
                    arguments=tool_use.input,
                    user_id=user_id,
                    session_id=credential_session_id if not user_id else None,
                    db=db,
                )

                # Extract text content from result
                result_text = ""
                if result:
                    for content in result:
                        if hasattr(content, "text"):
                            result_text += content.text

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_text,
                })

                tool_calls_made.append({
                    "name": tool_use.name,
                    "arguments": tool_use.input,
                    "result": result_text[:200],  # Truncate for brevity
                })

                LLM_METRICS["total_tool_calls"] += 1

            except asyncio.TimeoutError:
                logger.error(f"Tool call {tool_use.name} timed out")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": "Error: Tool execution timed out",
                    "is_error": True,
                })
            except (ConnectionError, OSError) as e:
                logger.error(f"Tool call {tool_use.name} connection error: {str(e)}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": f"Error: Connection failed - {str(e)}",
                    "is_error": True,
                })
            except ValueError as e:
                logger.error(f"Tool call {tool_use.name} validation error: {str(e)}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": f"Error: Invalid parameters - {str(e)}",
                    "is_error": True,
                })

        return tool_results

    async def execute_tools_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls in parallel for speed.

        Args:
            tool_calls: List of tool calls with 'tool' and 'args' keys
            datasource: Active datasource
            credential_session_id: Session ID for credentials
            user_id: User ID for credentials
            db: Database session

        Returns:
            List of results with 'tool', 'success', and 'result'/'error' keys
        """
        start_time = time.time()

        async def execute_single_tool(tool_call: Dict[str, Any]) -> Dict[str, Any]:
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
            except asyncio.TimeoutError:
                logger.error(f"Tool {tool_name} timed out")
                return {
                    "tool": tool_name,
                    "success": False,
                    "error": "Tool execution timed out",
                }
            except (ConnectionError, OSError) as e:
                logger.error(f"Tool {tool_name} connection error: {e}")
                return {
                    "tool": tool_name,
                    "success": False,
                    "error": f"Connection error: {str(e)}",
                }
            except ValueError as e:
                logger.error(f"Tool {tool_name} invalid input: {e}")
                return {
                    "tool": tool_name,
                    "success": False,
                    "error": f"Invalid input: {str(e)}",
                }

        # Execute all tools in parallel
        results = await asyncio.gather(
            *[execute_single_tool(tc) for tc in tool_calls],
            return_exceptions=True
        )

        elapsed = time.time() - start_time
        LLM_METRICS["tool_execution_time"].append(elapsed)
        logger.info(f"⚡ Parallel tool execution completed in {elapsed:.2f}s ({len(tool_calls)} tools)")

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

    def get_llm_stats(self) -> Dict[str, Any]:
        """Get LLM interaction statistics."""
        gen_times = LLM_METRICS["sonnet_generation_time"]
        tool_times = LLM_METRICS["tool_execution_time"]
        return {
            "total_tool_calls": LLM_METRICS["total_tool_calls"],
            "avg_generation_time_ms": (sum(gen_times) / len(gen_times) * 1000) if gen_times else 0,
            "avg_tool_execution_time_ms": (sum(tool_times) / len(tool_times) * 1000) if tool_times else 0,
        }


# Global instance for import
claude_interaction_service = ClaudeInteractionService()

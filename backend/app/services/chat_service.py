"""
Chat service for handling LLM interactions.

This is the core orchestration service that coordinates:
- Message processing and session management
- Tool routing (via tool_routing_service)
- Parameter injection (via parameter_injection_service)
- Response formatting (via response_formatter)
"""

import logging
import asyncio
import time
import random
import functools
from typing import List, Dict, AsyncGenerator, Optional
from concurrent.futures import ThreadPoolExecutor

from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock
from anthropic import APIStatusError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.mcp_service import mcp_service
from app.services.credential_service import credential_service
from app.models.database import ChatHistory
from app.services.parameter_injection_service import parameter_injection_service
from app.services.response_formatter import response_formatter
from app.services.tool_routing_service import tool_routing_service
from app.services.claude_client import get_quirky_thinking_message  # Use shared function

logger = logging.getLogger(__name__)

# Thread pool for running synchronous Anthropic streaming in background
_stream_executor = ThreadPoolExecutor(max_workers=10)


async def retry_on_overload_async(coro_func, *args, max_retries=3, base_delay=1.0, **kwargs):
    """
    Async retry helper for Claude API calls on overload errors.
    Uses asyncio.sleep() to avoid blocking the event loop.

    Usage: result = await retry_on_overload_async(client.messages.create, **params)
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            # Run the synchronous API call in executor to not block
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: coro_func(*args, **kwargs))
            return result
        except APIStatusError as e:
            if e.status_code == 529 or "overloaded" in str(e).lower():
                last_error = e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)  # Non-blocking sleep
            else:
                raise
        except Exception as e:
            if "overloaded" in str(e).lower():
                last_error = e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)  # Non-blocking sleep
            else:
                raise
    logger.error(f"Claude API still overloaded after {max_retries} retries")
    raise last_error or Exception("Claude API overloaded - please try again in a moment")


def retry_on_overload(func):
    """
    Sync decorator for retrying Claude API calls on overload errors.

    Usage:
        @retry_on_overload
        def call_api():
            return client.messages.create(...)
        response = call_api()
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1.0
        last_error = None

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except APIStatusError as e:
                if e.status_code == 529 or "overloaded" in str(e).lower():
                    last_error = e
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    raise
            except Exception as e:
                if "overloaded" in str(e).lower():
                    last_error = e
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    raise

        logger.error(f"Claude API still overloaded after {max_retries} retries")
        raise last_error or Exception("Claude API overloaded - please try again in a moment")

    return wrapper


# NOTE: get_quirky_thinking_message is imported from claude_client to avoid duplication


class ChatService:
    """
    Service for handling chat interactions with Claude and MCP tools.

    Session Architecture (Production-Ready):
    - Chat history is persisted to MySQL database via ChatHistory model
    - Sessions are tied to user_id + session_id for multi-device support
    - No in-memory state = horizontally scalable (any instance can serve any user)
    - For Redis-backed sessions, replace get_chat_history/save_chat_history

    Note: This service is stateless by design. All session state is in the database.
    """

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        # NOTE: Session storage is DATABASE-BACKED via ChatHistory model
        # See save_chat_history() and get_chat_history() methods
        # This allows horizontal scaling - any server instance can serve any user

    # =========================================================================
    # SESSION & HISTORY MANAGEMENT (Database-backed for production)
    # =========================================================================

    async def save_chat_history(
        self,
        user_id: str,
        session_id: str,
        datasource: str,
        messages: List[dict],
        db: AsyncSession,
    ) -> None:
        """Save chat history to database for authenticated users."""
        try:
            saved_count = 0
            for message in messages:
                content = message.get("content")
                if not content or not str(content).strip():
                    continue

                chat_record = ChatHistory(
                    user_id=user_id,
                    session_id=session_id,
                    datasource=datasource,
                    role=message.get("role"),
                    content=content,
                )
                db.add(chat_record)
                saved_count += 1

            await db.commit()
            logger.info(f"Saved {saved_count} messages to chat history for user {user_id[:8]}...")
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to save chat history: {str(e)}")
            raise

    async def get_chat_history(
        self,
        user_id: str,
        datasource: str,
        session_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """Get chat history from database for authenticated users."""
        if not db:
            return []

        try:
            query = select(ChatHistory).where(
                ChatHistory.user_id == user_id,
                ChatHistory.datasource == datasource,
            )
            if session_id:
                query = query.where(ChatHistory.session_id == session_id)
            query = query.order_by(ChatHistory.created_at.asc())

            result = await db.execute(query)
            chat_records = result.scalars().all()

            messages = []
            for record in chat_records:
                msg = record.to_dict()
                if msg.get("content") and str(msg.get("content", "")).strip():
                    messages.append(msg)

            logger.info(f"Retrieved {len(messages)} messages from chat history")
            return messages
        except Exception as e:
            # Log at warning level - this is a graceful degradation, not a critical failure
            # User can still chat, just without context from previous messages
            logger.warning(f"Failed to get chat history (graceful degradation): {str(e)}")
            logger.debug(f"Chat history error details", exc_info=True)
            return []  # Return empty list to allow chat to continue without history

    async def _get_session_messages(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        datasource: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """Get messages for a session from database."""
        if user_id and db and datasource:
            return await self.get_chat_history(
                user_id=user_id,
                datasource=datasource,
                session_id=session_id,
                db=db,
            )
        return []

    # =========================================================================
    # SYSTEM PROMPT & TOOLS
    # =========================================================================

    async def _get_tools(self, datasource: str) -> List[dict]:
        """Get available tools from MCP server with caching."""
        return await mcp_service.get_cached_tools(datasource)

    def _create_system_prompt(self, datasource: str) -> str:
        """Create system prompt for Claude using connector registry."""
        from app.connectors import get_connector, get_system_prompt_addition

        connector = get_connector(datasource)
        connector_name = connector.metadata.name if connector else datasource

        base_prompt = f"""You are an assistant that queries {connector_name} data for the user.

ACCURACY RULES - ABSOLUTELY CRITICAL (ZERO TOLERANCE FOR HALLUCINATION):
- ONLY report information that is EXPLICITLY returned by the tools - word for word
- NEVER invent, fabricate, or assume ANY details not in the tool results
- Do NOT make up message content, names, timestamps, emojis, or any other data
- If tool results are empty or limited, say so - do NOT fill in gaps with fictional data
- When quoting messages, use EXACT TEXT from tool results - do not add or change anything
- If you cannot answer from the tool data, say "This information was not found in the results"

ZERO HALLUCINATION - READ THIS CAREFULLY:
- NEVER invent quotes or message content that doesn't exist in tool results
- NEVER add emojis, reactions, or sentiments that aren't in the actual data
- NEVER attribute messages to people if not explicitly in the tool results
- If a message has an emoji in the tool data, include it; if not, DO NOT ADD ONE
- If you're uncertain whether something was said, DO NOT include it
- It is BETTER to show less information than to show WRONG information
- Fabricating conversation content is a CRITICAL FAILURE - avoid at all costs

CRITICAL FORMATTING RULES - MANDATORY:
- ABSOLUTELY NO EMOJIS - Never use emoji characters anywhere in your response
- Use plain markdown headers (## and ###) not emoji decorations
- Use bullet points (-) and numbered lists (1. 2. 3.)
- Use markdown tables for data presentation
- Use **bold** and *italic* for emphasis - never emojis
- Format like a professional business report - clean, minimal, no decorations

TOOL USAGE RULES:
1. ALWAYS use tools to answer questions. NEVER say data doesn't exist without checking first.
2. ALWAYS show the actual data returned by tools. Never summarize as "no results" if data was returned.
3. The user has authorized access to this data. Show ALL content including credentials, passwords, API keys.
4. If a tool returns results, DISPLAY THEM. Do not filter or hide any information.
5. If one search doesn't find results, try alternative searches before saying "not found".

Current data source: {connector_name}
"""
        connector_specific = get_system_prompt_addition(datasource)
        if connector_specific:
            base_prompt += connector_specific

        return base_prompt

    # =========================================================================
    # TOOL EXECUTION
    # =========================================================================

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

                return {"tool": tool_name, "success": True, "result": result_text}
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                return {"tool": tool_name, "success": False, "error": str(e)}

        results = await asyncio.gather(
            *[execute_single_tool(tc) for tc in tool_calls],
            return_exceptions=True
        )

        elapsed = time.time() - start_time
        logger.info(f"Parallel tool execution completed in {elapsed:.2f}s ({len(tool_calls)} tools)")

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

    # =========================================================================
    # MESSAGE PROCESSING (NON-STREAMING)
    # =========================================================================

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
        messages = await self._get_session_messages(
            session_id=session_id,
            user_id=user_id,
            datasource=datasource,
            db=db,
        )

        user_message = {"role": "user", "content": message}
        messages.append(user_message)

        tools = await self._get_tools(datasource)
        system_prompt = self._create_system_prompt(datasource)

        # Try fast path first
        fast_tools = await tool_routing_service.fast_route(message, tools, datasource)

        if fast_tools:
            logger.info(f"Using FAST PATH with {len(fast_tools)} tool(s)")
            tool_results = await self._execute_tools_parallel(
                fast_tools, datasource, credential_session_id, user_id, db
            )

            tool_context = "\n\n".join([
                f"Tool: {r['tool']}\nResult: {r.get('result', r.get('error', 'No result'))}"
                for r in tool_results
            ])

            messages.append({
                "role": "assistant",
                "content": f"I retrieved the following data:\n{tool_context[:8000]}"
            })
            messages.append({
                "role": "user",
                "content": "Based on the data above, please provide a clear, well-formatted response to my original question."
            })

            @retry_on_overload
            def create_response():
                return self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                )
            response = create_response()

            response_text = response.content[0].text if response.content else ""
            tool_calls = [{"tool": t.get("tool") or t.get("name"), "args": t.get("args") or t.get("arguments", {})} for t in fast_tools]
        else:
            response_text, tool_calls = await self._call_claude(
                messages, tools, system_prompt, datasource, credential_session_id, user_id, db
            )

        assistant_message = {"role": "assistant", "content": response_text}
        messages.append(assistant_message)

        if user_id and db:
            try:
                await self.save_chat_history(
                    user_id=user_id,
                    session_id=session_id,
                    datasource=datasource,
                    messages=[user_message, assistant_message],
                    db=db,
                )
            except Exception as e:
                logger.error(f"Failed to save chat history: {str(e)}")

        return response_text, tool_calls

    # =========================================================================
    # MESSAGE PROCESSING (STREAMING)
    # =========================================================================

    # Datasources that require per-user OAuth (no fallback to default credentials)
    OAUTH_REQUIRED_DATASOURCES = {"slack", "github", "jira"}

    async def process_message_stream(
        self,
        message: str,
        datasource: str,
        session_id: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[str, None]:
        """Process a chat message with streaming response."""
        start_time = time.time()

        # EARLY CHECK: For OAuth-required datasources, verify user has connected
        if datasource.lower() in self.OAUTH_REQUIRED_DATASOURCES:
            if user_id and db:
                has_creds = await credential_service.has_credentials(
                    datasource=datasource,
                    db=db,
                    user_id=user_id,
                )
                if not has_creds:
                    error_msg = f"## Connect Your {datasource.title()} Account\n\nYou need to connect your {datasource.title()} account before you can use this feature.\n\n**To connect:**\n1. Click the **Settings** icon (gear) in the sidebar\n2. Select **{datasource.title()}**\n3. Click **Connect with {datasource.title()}**\n\nOnce connected, you'll be able to access your {datasource.title()} data."
                    yield {"type": "text", "content": error_msg}
                    return

        force_refresh = mcp_service.should_force_refresh(message)

        # Check ultra-fast path (skip Claude entirely for simple queries)
        if tool_routing_service.can_use_ultra_fast_path(message, datasource):
            direct_tools = tool_routing_service.direct_route(message, datasource)
            if direct_tools and len(direct_tools) == 1:
                tool_call = direct_tools[0]
                try:
                    result = await mcp_service.call_tool(
                        datasource=datasource,
                        tool_name=tool_call["tool"],
                        arguments=tool_call.get("args", {}),
                        user_id=user_id,
                        session_id=credential_session_id if not user_id else None,
                        db=db,
                        force_refresh=force_refresh,
                    )

                    result_text = ""
                    if result:
                        for content in result:
                            if hasattr(content, "text"):
                                result_text += content.text

                    formatted = response_formatter.format_ultra_fast_response(
                        datasource, tool_call["tool"], result_text
                    )
                    if formatted:
                        import re
                        words = re.findall(r'\S+\s*|\n+', formatted)
                        for word in words:
                            yield {"type": "text", "content": word}

                        # Save to history
                        messages = await self._get_session_messages(session_id, user_id, datasource, db)
                        user_message = {"role": "user", "content": message}
                        assistant_message = {"role": "assistant", "content": formatted}
                        messages.extend([user_message, assistant_message])

                        if user_id and db:
                            try:
                                await self.save_chat_history(user_id, session_id, datasource, [user_message, assistant_message], db)
                            except Exception as e:
                                logger.error(f"Failed to save chat history: {str(e)}")

                        return
                except Exception as e:
                    logger.warning(f"Ultra-fast path failed, falling back: {e}")

        # Immediate feedback
        immediate_feedback = response_formatter.get_immediate_feedback_message(datasource, message)
        yield {"type": "thinking", "content": f"Querying {datasource}"}
        yield {"type": "text", "content": immediate_feedback + "\n\n"}

        messages = await self._get_session_messages(
            session_id=session_id,
            user_id=user_id,
            datasource=datasource,
            db=db,
        )

        user_message = {"role": "user", "content": message}
        messages.append(user_message)

        tools = await self._get_tools(datasource)
        system_prompt = self._create_system_prompt(datasource)

        # Try fast path
        fast_tools = await tool_routing_service.fast_route(message, tools, datasource)

        if fast_tools:
            logger.info(f"Using FAST PATH with {len(fast_tools)} tool(s)")
            yield "*Found relevant data...*\n\n"

            tool_results = await self._execute_tools_parallel(
                fast_tools, datasource, credential_session_id, user_id, db
            )

            tool_context = "\n\n".join([
                f"Tool: {r['tool']}\nResult: {r.get('result', r.get('error', 'No result'))}"
                for r in tool_results
            ])

            messages.append({
                "role": "assistant",
                "content": f"I retrieved the following data:\n{tool_context[:2000]}"
            })
            messages.append({
                "role": "user",
                "content": "Based on the data above, please provide a clear, well-formatted response to my original question."
            })

            full_response = ""
            queue: asyncio.Queue = asyncio.Queue()

            def run_fast_stream():
                try:
                    stream = self.client.messages.stream(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                    )
                    with stream as event_stream:
                        for event in event_stream:
                            if event.type == "content_block_delta":
                                if hasattr(event.delta, "text"):
                                    queue.put_nowait({"type": "text", "content": event.delta.text})
                    queue.put_nowait(None)
                except Exception as e:
                    logger.error(f"Fast stream error: {e}")
                    queue.put_nowait({"type": "error", "error": str(e)})
                    queue.put_nowait(None)

            loop = asyncio.get_running_loop()
            stream_task = loop.run_in_executor(_stream_executor, run_fast_stream)

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                    if event is None:
                        break
                    if event.get("type") == "text":
                        full_response += event["content"]
                        yield {"type": "text", "content": event["content"]}
                    elif event.get("type") == "error":
                        yield {"type": "text", "content": f"\n\nError: {event['error']}"}
                        break
                except asyncio.TimeoutError:
                    break

            await stream_task
        else:
            # Standard path with full tool loop
            logger.info("Using STANDARD PATH (complex query)")
            yield {"type": "thinking", "content": "Analyzing your request..."}

            full_response = ""
            async for event in self._call_claude_stream(messages, tools, system_prompt, datasource, credential_session_id, user_id, db):
                if isinstance(event, dict):
                    if event.get("type") == "text":
                        full_response += event.get("content", "")
                    yield event
                else:
                    full_response += str(event)
                    yield event

        # Save to history
        assistant_message = {"role": "assistant", "content": full_response}
        messages.append(assistant_message)

        if user_id and db:
            try:
                await self.save_chat_history(
                    user_id=user_id,
                    session_id=session_id,
                    datasource=datasource,
                    messages=[user_message, assistant_message],
                    db=db,
                )
            except Exception as e:
                logger.error(f"Failed to save chat history: {str(e)}")

    # =========================================================================
    # CLAUDE API CALLS
    # =========================================================================

    async def _call_claude(
        self,
        messages: List[dict],
        tools: List[dict],
        system_prompt: str,
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> tuple[str, List[dict]]:
        """Call Claude API with tool support (non-streaming)."""
        tool_calls_made = []
        max_iterations = 25
        recent_tool_calls = []  # Track recent tool calls to detect loops

        for iteration in range(max_iterations):
            # Loop detection: if same tool called 3+ times in a row, break
            if len(recent_tool_calls) >= 3:
                last_three = recent_tool_calls[-3:]
                if len(set(last_three)) == 1:
                    logger.warning(f"Loop detected: {last_three[0]} called 3 times in a row, breaking")
                    return f"I was having trouble querying the {datasource} database. The tool '{last_three[0]}' was called multiple times without progress. Please try a more specific query.", tool_calls_made
            @retry_on_overload
            def call_claude_api():
                return self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=tools if tools else None,
                )
            response = call_claude_api()

            tool_use_blocks = [
                block for block in response.content if isinstance(block, ToolUseBlock)
            ]

            if not tool_use_blocks:
                text_blocks = [
                    block for block in response.content if isinstance(block, TextBlock)
                ]
                response_text = "\n".join(block.text for block in text_blocks)
                return response_text, tool_calls_made

            tool_results = []
            for tool_use in tool_use_blocks:
                # Track tool calls for loop detection
                recent_tool_calls.append(tool_use.name)

                # Inject missing parameters using the service
                tool_use.input = parameter_injection_service.inject_parameters(
                    tool_use.name,
                    tool_use.input,
                    datasource,
                    messages,
                )

                # Check if parameter injection set an error (e.g., missing query)
                if "_error" in tool_use.input:
                    error_msg = tool_use.input.pop("_error")
                    logger.warning(f"Parameter injection error for {tool_use.name}: {error_msg}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {error_msg}",
                        "is_error": True,
                    })
                    continue

                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
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

                    tool_calls_made.append({
                        "name": tool_use.name,
                        "arguments": tool_use.input,
                        "result": result_text[:200],
                    })

                except Exception as e:
                    logger.error(f"Tool call failed: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return "I apologize, but I encountered an issue processing your request. Please try rephrasing your question.", tool_calls_made

    async def _call_claude_stream(
        self,
        messages: List[dict],
        tools: List[dict],
        system_prompt: str,
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[str, None]:
        """Call Claude API with streaming, extended thinking, and tool support."""
        max_iterations = 25
        recent_tool_calls = []  # Track recent tool calls to detect loops

        for iteration in range(max_iterations):
            # Loop detection: if same tool called 3+ times in a row, break
            if len(recent_tool_calls) >= 3:
                last_three = recent_tool_calls[-3:]
                if len(set(last_three)) == 1:
                    logger.warning(f"Loop detected: {last_three[0]} called 3 times in a row, breaking")
                    yield {"type": "text", "content": f"\n\nI was having trouble querying the {datasource} database. The tool '{last_three[0]}' was called multiple times without making progress. Please try a more specific query (e.g., 'SELECT * FROM providers LIMIT 10')."}
                    return
            queue: asyncio.Queue = asyncio.Queue()
            final_message_holder = {"message": None}

            def run_claude_stream():
                try:
                    stream_params = {
                        "model": "claude-sonnet-4-5-20250929",
                        "max_tokens": 16000,
                        "system": system_prompt,
                        "messages": messages,
                    }
                    if tools:
                        stream_params["tools"] = tools
                    stream_params["thinking"] = {"type": "enabled", "budget_tokens": 4000}

                    stream = self.client.messages.stream(**stream_params)
                    with stream as event_stream:
                        current_block_type = None
                        for event in event_stream:
                            if event.type == "content_block_start":
                                if hasattr(event.content_block, "type"):
                                    current_block_type = event.content_block.type
                                    if current_block_type == "thinking":
                                        queue.put_nowait({"type": "thinking_start"})
                                    elif current_block_type == "tool_use":
                                        queue.put_nowait({"type": "tool_start", "block": event.content_block})
                            elif event.type == "content_block_delta":
                                if hasattr(event.delta, "thinking"):
                                    queue.put_nowait({"type": "thinking", "content": event.delta.thinking})
                                elif hasattr(event.delta, "text"):
                                    queue.put_nowait({"type": "text", "content": event.delta.text})
                            elif event.type == "content_block_stop":
                                if current_block_type == "thinking":
                                    queue.put_nowait({"type": "thinking_end"})
                                current_block_type = None
                        final_message_holder["message"] = event_stream.get_final_message()
                    queue.put_nowait(None)
                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    queue.put_nowait({"type": "error", "error": str(e)})
                    queue.put_nowait(None)

            loop = asyncio.get_running_loop()
            stream_task = loop.run_in_executor(_stream_executor, run_claude_stream)

            tool_use_blocks = []

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120.0)
                    if event is None:
                        break
                    event_type = event.get("type")

                    if event_type == "thinking_start":
                        yield {"type": "thinking_start"}
                    elif event_type == "thinking":
                        yield {"type": "thinking", "content": event["content"]}
                    elif event_type == "thinking_end":
                        yield {"type": "thinking_end"}
                    elif event_type == "text":
                        yield {"type": "text", "content": event["content"]}
                    elif event_type == "tool_start":
                        tool_use_blocks.append(event["block"])
                    elif event_type == "error":
                        yield {"type": "text", "content": f"\n\nError: {event['error']}"}
                        break
                except asyncio.TimeoutError:
                    break

            await stream_task

            final_message = final_message_holder["message"]

            if not tool_use_blocks and final_message:
                tool_use_blocks = [
                    block for block in final_message.content
                    if isinstance(block, ToolUseBlock)
                ]

            if not tool_use_blocks:
                return

            yield "\n\n"

            tool_results = []
            for tool_use in tool_use_blocks:
                # Track tool calls for loop detection
                recent_tool_calls.append(tool_use.name)

                # Inject missing parameters using the service
                tool_use.input = parameter_injection_service.inject_parameters(
                    tool_use.name,
                    tool_use.input,
                    datasource,
                    messages,
                )

                # Check if parameter injection set an error (e.g., missing query)
                if "_error" in tool_use.input:
                    error_msg = tool_use.input.pop("_error")
                    logger.warning(f"Parameter injection error for {tool_use.name}: {error_msg}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {error_msg}",
                        "is_error": True,
                    })
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": error_msg}
                    continue

                tool_feedback = get_quirky_thinking_message(tool_use.name)
                yield {"type": "tool_start", "tool": tool_use.name, "description": tool_feedback}

                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
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

                    yield {"type": "tool_end", "tool": tool_use.name, "success": True}

                except Exception as e:
                    logger.error(f"Tool call failed: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True,
                    })
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": str(e)}

            messages.append({"role": "assistant", "content": final_message.content})
            messages.append({"role": "user", "content": tool_results})

            yield "\n"

        yield "\n\nI apologize, but I encountered an issue processing your request. Please try rephrasing your question."


# Global chat service instance
chat_service = ChatService()

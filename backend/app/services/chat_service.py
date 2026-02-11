"""
Chat service for handling LLM interactions.

SIMPLIFIED VERSION: Let Claude handle everything.
No more parameter injection, no more fast routing, no more ultra-fast path.
Claude is smart enough to call the right tools with the right parameters.
"""

import logging
import asyncio
import time
import random
from typing import List, AsyncGenerator, Optional
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
from app.services.claude_client import get_quirky_thinking_message

logger = logging.getLogger(__name__)

# Thread pool for running synchronous Anthropic streaming in background
# Each concurrent streaming chat uses one thread; size limits max concurrent streams
_stream_executor = ThreadPoolExecutor(max_workers=50)

# In-memory session storage for anonymous users (no database)
# Key: session_id, Value: {"messages": [...], "last_accessed": float}
_anonymous_sessions: dict[str, dict] = {}
_SESSION_MAX_MESSAGES = 50  # Limit to prevent memory bloat
_SESSION_TTL_SECONDS = 3600  # 1 hour TTL for anonymous sessions
_SESSION_MAX_COUNT = 500  # Max total sessions to prevent unbounded growth
_last_cleanup_time = 0.0


def _extract_multimodal_content(result, logger, tool_name=""):
    """Extract text, image, and PDF content from MCP tool result blocks.

    MCP tool results can contain TextContent, ImageContent, etc.
    This function handles all types and converts images/PDFs to Claude API format.
    """
    result_text = ""
    image_blocks = []
    pdf_blocks = []

    CLAUDE_MIME_MAP = {
        "image/jpeg": "image/jpeg", "image/png": "image/png",
        "image/gif": "image/gif", "image/webp": "image/webp",
    }

    if not result:
        return result_text, image_blocks, pdf_blocks

    for content in result:
        content_type = getattr(content, "type", None)
        logger.debug(f"[multimodal] {tool_name}: block type={content_type}, class={type(content).__name__}, attrs={[a for a in dir(content) if not a.startswith('_')][:10]}")

        if content_type == "image":
            # MCP ImageContent → Claude API image block
            data = getattr(content, "data", None)
            mime = getattr(content, "mimeType", None)
            if data and mime:
                media_type = CLAUDE_MIME_MAP.get(mime, "image/png")
                image_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    }
                })
                logger.info(f"[multimodal] {tool_name}: captured image block ({mime}, {len(data)} chars base64)")
            else:
                logger.warning(f"[multimodal] {tool_name}: image block missing data/mimeType: data={bool(data)}, mime={mime}")
        elif hasattr(content, "text"):
            text = content.text
            if text.startswith("__PDF_BASE64__:"):
                b64_data = text[len("__PDF_BASE64__:"):]
                pdf_blocks.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": b64_data,
                    }
                })
                logger.info(f"[multimodal] {tool_name}: captured PDF block ({len(b64_data)} chars base64)")
            else:
                result_text += text
        else:
            logger.warning(f"[multimodal] {tool_name}: unhandled content block type={content_type}, class={type(content).__name__}")

    logger.info(f"[multimodal] {tool_name}: extracted {len(result_text)} chars text, {len(image_blocks)} images, {len(pdf_blocks)} PDFs")
    return result_text, image_blocks, pdf_blocks


def _cleanup_expired_sessions() -> None:
    """Remove expired anonymous sessions. Called periodically."""
    global _last_cleanup_time
    now = time.time()

    # Only run cleanup every 5 minutes
    if now - _last_cleanup_time < 300:
        return
    _last_cleanup_time = now

    expired = [
        sid for sid, data in _anonymous_sessions.items()
        if now - data.get("last_accessed", 0) > _SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del _anonymous_sessions[sid]

    if expired:
        logger.info(f"Cleaned up {len(expired)} expired anonymous sessions, {len(_anonymous_sessions)} remaining")

    # If still over max count, evict oldest
    if len(_anonymous_sessions) > _SESSION_MAX_COUNT:
        sorted_sessions = sorted(
            _anonymous_sessions.items(),
            key=lambda x: x[1].get("last_accessed", 0),
        )
        to_remove = len(_anonymous_sessions) - _SESSION_MAX_COUNT
        for sid, _ in sorted_sessions[:to_remove]:
            del _anonymous_sessions[sid]
        logger.info(f"Evicted {to_remove} oldest anonymous sessions (over {_SESSION_MAX_COUNT} limit)")


def _format_exception_message(e: Exception) -> str:
    """
    Format exception message, extracting nested errors from ExceptionGroup/TaskGroup.
    """
    if hasattr(e, 'exceptions') and e.exceptions:
        nested_msgs = []
        for nested in e.exceptions[:3]:
            nested_msgs.append(str(nested))
        return "; ".join(nested_msgs) if nested_msgs else str(e)
    return str(e)


async def retry_on_overload_async(coro_func, *args, max_retries=3, base_delay=1.0, **kwargs):
    """Async retry helper for Claude API calls on overload errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: coro_func(*args, **kwargs))
            return result
        except APIStatusError as e:
            if e.status_code == 529 or "overloaded" in str(e).lower():
                last_error = e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as e:
            if "overloaded" in str(e).lower():
                last_error = e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                raise
    logger.error(f"Claude API still overloaded after {max_retries} retries")
    raise last_error or Exception("Claude API overloaded - please try again in a moment")


class ChatService:
    """
    Service for handling chat interactions with Claude and MCP tools.

    SIMPLIFIED: Let Claude handle tool selection and parameter extraction.
    Uses Haiku for simple queries, Sonnet for complex ones.
    """

    # Simple query patterns that Haiku can handle (direct tool calls, minimal reasoning)
    SIMPLE_QUERY_PATTERNS = [
        # List-type queries
        r"^list\s+(all\s+)?(buckets?|projects?|channels?|users?|emails?|messages?|calendars?|events?|files?|docs?|tasks?)\.?$",
        r"^show\s+(me\s+)?(the\s+)?(all\s+)?(buckets?|projects?|channels?|users?)\.?$",
        r"^what\s+(buckets?|projects?|channels?)\s+(do\s+i\s+have|are\s+there)\.?$",
        r"^get\s+(all\s+)?(buckets?|projects?|channels?|users?|emails?|messages?)\.?$",
        # Email queries - "show me last N emails", "get my recent emails"
        r"^(show\s+me\s+|get\s+|fetch\s+)?(my\s+)?(the\s+)?(last|recent|latest)\s+\d+\s+(emails?|messages?)\.?$",
        r"^(show\s+me\s+|get\s+|fetch\s+)?(my\s+)?(the\s+)?inbox\.?$",
        r"^(what|check)\s+(are\s+)?(my\s+)?(recent|latest|new)\s+(emails?|messages?)\.?$",
        # Calendar queries
        r"^(show\s+me\s+|get\s+|what\s+are\s+)?(my\s+)?(today'?s?|upcoming|next)\s+(meetings?|events?|calendar)\.?$",
        # Simple Slack queries
        r"^(show\s+me\s+|get\s+|read\s+)?(the\s+)?(last|recent)\s+\d+\s+messages?\s+(in|from)\s+#?\w+\.?$",
    ]

    # Model selection
    MODEL_HAIKU = "claude-3-5-haiku-20241022"
    MODEL_SONNET = "claude-sonnet-4-5-20250929"

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        import re
        self._simple_patterns = [re.compile(p, re.IGNORECASE) for p in self.SIMPLE_QUERY_PATTERNS]

    def _is_simple_query(self, message: str, has_context: bool) -> bool:
        """
        Check if a query is simple enough for Haiku.

        Simple = single list-type tool, no parameters, no reasoning needed.
        Conservative: if in doubt, use Sonnet.
        """
        # If there's conversation context, use Sonnet (might need reasoning)
        if has_context:
            return False

        # Check against simple patterns
        message_clean = message.strip().lower()
        for pattern in self._simple_patterns:
            if pattern.match(message_clean):
                return True

        return False

    def _select_model(self, message: str, has_context: bool) -> str:
        """Select the appropriate model based on query complexity.

        Haiku: Fast, good for simple tool calls (list, fetch, show N items)
        Sonnet: Better reasoning, needed for complex queries and follow-ups
        """
        if self._is_simple_query(message, has_context):
            logger.info(f"Using HAIKU for simple query: {message[:50]}...")
            return self.MODEL_HAIKU

        logger.info(f"Using SONNET for query: {message[:50]}...")
        return self.MODEL_SONNET

    # =========================================================================
    # SESSION & HISTORY MANAGEMENT
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
            logger.warning(f"Failed to get chat history (graceful degradation): {str(e)}")
            return []

    async def _get_session_messages(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        datasource: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """Get messages for a session from database or in-memory store."""
        # Authenticated users: load from database
        if user_id and db and datasource:
            return await self.get_chat_history(
                user_id=user_id,
                datasource=datasource,
                session_id=session_id,
                db=db,
            )

        # Anonymous users: load from in-memory store
        _cleanup_expired_sessions()
        if session_id in _anonymous_sessions:
            session_data = _anonymous_sessions[session_id]
            session_data["last_accessed"] = time.time()
            return session_data["messages"].copy()

        return []

    def _save_anonymous_session(self, session_id: str, messages: List[dict]) -> None:
        """Save messages to in-memory store for anonymous users."""
        # Keep only last N messages to prevent memory bloat
        if len(messages) > _SESSION_MAX_MESSAGES:
            messages = messages[-_SESSION_MAX_MESSAGES:]
        _anonymous_sessions[session_id] = {
            "messages": messages,
            "last_accessed": time.time(),
        }

    # =========================================================================
    # SYSTEM PROMPT & TOOLS
    # =========================================================================

    async def _get_tools(self, datasource: str) -> List[dict]:
        """Get available tools from MCP server with caching."""
        return await mcp_service.get_cached_tools(datasource)

    def _create_system_prompt(self, datasource: str, query: str = "") -> str:
        """Create system prompt for Claude using centralized prompts.

        Args:
            datasource: The datasource being queried
            query: The user's query (unused - classifier disabled for now)
        """
        from app.connectors import get_connector
        from app.core.prompts import Prompts

        connector = get_connector(datasource)
        connector_name = connector.metadata.name if connector else datasource

        return Prompts.get_agentic_prompt(datasource, connector_name)

    # =========================================================================
    # TOOL EXECUTION
    # =========================================================================

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict,
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Execute a single tool call."""
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
            error_msg = _format_exception_message(e)
            logger.error(f"Tool {tool_name} failed: {error_msg}")
            return {"tool": tool_name, "success": False, "error": error_msg}

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

        # Select model based on query complexity (Haiku for simple, Sonnet for complex)
        has_context = len(messages) > 0
        model = self._select_model(message, has_context)

        user_message = {"role": "user", "content": message}
        messages.append(user_message)

        tools = await self._get_tools(datasource)
        system_prompt = self._create_system_prompt(datasource, message)

        # Let Claude handle everything
        response_text, tool_calls = await self._call_claude(
            messages, tools, system_prompt, datasource, model, credential_session_id, user_id, db
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
        else:
            # Anonymous user: save to in-memory store
            self._save_anonymous_session(session_id, messages)

        return response_text, tool_calls

    # =========================================================================
    # MESSAGE PROCESSING (STREAMING)
    # =========================================================================

    # Datasources that require per-user OAuth (no fallback to default credentials)
    OAUTH_REQUIRED_DATASOURCES = {"slack", "github", "jira", "google_workspace"}

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
                    ds_display = "Google Workspace" if datasource.lower() == "google_workspace" else datasource.replace("_", " ").title()
                    error_msg = f"## Connect Your {ds_display} Account\n\nYou need to connect your {ds_display} account before you can use this feature.\n\n**To connect:**\n1. Click the **Settings** icon (gear) in the sidebar\n2. Select **{ds_display}**\n3. Click **Connect with {ds_display}**\n\nOnce connected, you'll be able to access your {ds_display} data."
                    yield {"type": "text", "content": error_msg}
                    return

        # Get session messages
        messages = await self._get_session_messages(
            session_id=session_id,
            user_id=user_id,
            datasource=datasource,
            db=db,
        )

        # Select model based on query complexity (Haiku for simple, Sonnet for complex)
        has_context = len(messages) > 0
        model = self._select_model(message, has_context)

        user_message = {"role": "user", "content": message}
        messages.append(user_message)

        tools = await self._get_tools(datasource)
        system_prompt = self._create_system_prompt(datasource, message)

        # Let Claude handle everything with streaming (no forced tool_choice - let Claude decide)
        logger.info(f"Using {model} for this query")
        yield {"type": "thinking", "content": "Analyzing your request..."}

        full_response = ""
        async for event in self._call_claude_stream(messages, tools, system_prompt, datasource, model, credential_session_id, user_id, db):
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
        else:
            # Anonymous user: save to in-memory store
            self._save_anonymous_session(session_id, messages)

    # =========================================================================
    # CLAUDE API CALLS
    # =========================================================================

    async def _call_claude(
        self,
        messages: List[dict],
        tools: List[dict],
        system_prompt: str,
        datasource: str,
        model: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> tuple[str, List[dict]]:
        """Call Claude API with tool support (non-streaming)."""
        tool_calls_made = []
        max_iterations = 10
        recent_tool_calls = []

        for iteration in range(max_iterations):
            # Loop detection: if same tool called 3+ times with IDENTICAL args, break
            if len(recent_tool_calls) >= 3:
                last_three = recent_tool_calls[-3:]
                names = [t[0] for t in last_three]
                args = [t[1] for t in last_three]
                if len(set(names)) == 1 and len(set(args)) == 1:
                    logger.warning(f"Loop detected: {names[0]} called 3 times with identical args, breaking")
                    search_tools = ["search_drive_files", "search_gmail_messages", "search_issues", "search_messages"]
                    if names[0] in search_tools:
                        return "I searched multiple times but no results were found. Please try rephrasing your query.", tool_calls_made
                    else:
                        return f"The tool '{names[0]}' was called multiple times without making progress. Please try rephrasing your query.", tool_calls_made

            response = await retry_on_overload_async(
                self.client.messages.create,
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None,
            )

            tool_use_blocks = [
                block for block in response.content if isinstance(block, ToolUseBlock)
            ]

            if not tool_use_blocks:
                text_blocks = [
                    block for block in response.content if isinstance(block, TextBlock)
                ]
                response_text = "\n".join(block.text for block in text_blocks)
                return response_text, tool_calls_made

            # Execute tool calls in PARALLEL for speed
            import json as _json

            async def execute_tool(tool_use):
                """Execute a single tool and return result dict."""
                recent_tool_calls.append((tool_use.name, _json.dumps(tool_use.input, sort_keys=True)))
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

                    result_text, image_blocks, pdf_blocks = _extract_multimodal_content(result, logger, tool_use.name)

                    # Check if the "successful" result is actually an auth error
                    if mcp_service._is_auth_error_message(result_text):
                        logger.warning(f"Auth error detected in tool result for {tool_use.name}: {result_text[:100]}")
                        return {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": "AUTHENTICATION_ERROR: The user needs to reconnect their account. Do NOT fabricate data. Tell the user to reconnect in Settings.",
                            "is_error": True,
                        }

                    tool_calls_made.append({
                        "name": tool_use.name,
                        "arguments": tool_use.input,
                        "result": result_text[:200],
                    })

                    # Build content: if images/PDFs present, use list format for Claude API
                    if image_blocks or pdf_blocks:
                        final_content = []
                        if result_text:
                            final_content.append({"type": "text", "text": result_text})
                        final_content.extend(image_blocks)
                        final_content.extend(pdf_blocks)
                        return {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": final_content,
                        }

                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    }

                except Exception as e:
                    error_msg = _format_exception_message(e)
                    logger.error(f"Tool call failed: {error_msg}")
                    # Check if this is an auth error — use clear, structured message
                    if mcp_service._is_auth_error_message(error_msg):
                        return {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": "AUTHENTICATION_ERROR: The user needs to reconnect their account. Do NOT fabricate data. Tell the user to reconnect in Settings.",
                            "is_error": True,
                        }
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"TOOL_ERROR: {error_msg}. Do NOT make up data. Report this error to the user.",
                        "is_error": True,
                    }

            # Run all tool calls in parallel
            if len(tool_use_blocks) > 1:
                logger.info(f"⚡ Executing {len(tool_use_blocks)} tools in PARALLEL")
            tool_results = await asyncio.gather(*[execute_tool(t) for t in tool_use_blocks])

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return "I apologize, but I encountered an issue processing your request. Please try rephrasing your question.", tool_calls_made

    async def _call_claude_stream(
        self,
        messages: List[dict],
        tools: List[dict],
        system_prompt: str,
        datasource: str,
        model: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        tool_choice: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """Call Claude API with streaming, extended thinking, and tool support.

        Args:
            tool_choice: Optional dict to force a specific tool. Use {"type": "tool", "name": "tool_name"}
                         to force Claude to use a specific tool. None lets Claude decide freely.
        """
        # Limit iterations - balance between completion and speed
        max_iterations = 5
        recent_tool_calls = []

        for iteration in range(max_iterations):
            # Loop detection
            if len(recent_tool_calls) >= 3:
                last_three = recent_tool_calls[-3:]
                names = [t[0] for t in last_three]
                args = [t[1] for t in last_three]
                if len(set(names)) == 1 and len(set(args)) == 1:
                    logger.warning(f"Loop detected: {names[0]} called 3 times with identical args, breaking")
                    search_tools = ["search_drive_files", "search_gmail_messages", "search_issues", "search_messages"]
                    if names[0] in search_tools:
                        yield {"type": "text", "content": f"\n\nI searched multiple times but no results were found. Please try rephrasing your query."}
                    else:
                        yield {"type": "text", "content": f"\n\nThe tool '{names[0]}' was called multiple times without making progress. Please try rephrasing your query."}
                    return

            queue: asyncio.Queue = asyncio.Queue()
            final_message_holder = {"message": None}

            def run_claude_stream():
                try:
                    stream_params = {
                        "model": model,
                        "max_tokens": 16000,
                        "system": system_prompt,
                        "messages": messages,
                    }
                    if tools:
                        stream_params["tools"] = tools
                    # Force specific tool on FIRST iteration only (if high confidence classification)
                    if tool_choice and iteration == 0:
                        stream_params["tool_choice"] = tool_choice
                        logger.info(f"🎯 Forcing tool_choice: {tool_choice}")
                    # NOTE: Extended thinking disabled - causes issues with multi-turn tool use
                    # stream_params["thinking"] = {"type": "enabled", "budget_tokens": 4000}

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

            # IMPORTANT: Always get tool_use_blocks from final_message, not from stream events
            # Stream events only give partial blocks without input arguments
            if final_message:
                tool_use_blocks = [
                    block for block in final_message.content
                    if isinstance(block, ToolUseBlock)
                ]

            if not tool_use_blocks:
                return

            yield "\n\n"

            import json as _json

            # Show all tools starting (for user feedback)
            for tool_use in tool_use_blocks:
                recent_tool_calls.append((tool_use.name, _json.dumps(tool_use.input, sort_keys=True)))
                tool_feedback = get_quirky_thinking_message(tool_use.name)
                yield {"type": "tool_start", "tool": tool_use.name, "description": tool_feedback}
                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

            # Execute all tools in PARALLEL
            async def execute_tool_stream(tool_use):
                """Execute a single tool and return (tool_use, result_dict, error)."""
                try:
                    result = await mcp_service.call_tool(
                        datasource=datasource,
                        tool_name=tool_use.name,
                        arguments=tool_use.input,
                        user_id=user_id,
                        session_id=credential_session_id if not user_id else None,
                        db=db,
                    )

                    result_text, image_blocks, pdf_blocks = _extract_multimodal_content(result, logger, tool_use.name)

                    # Check if the "successful" result is actually an auth error
                    if mcp_service._is_auth_error_message(result_text):
                        logger.warning(f"Auth error detected in tool result for {tool_use.name}: {result_text[:100]}")
                        return (tool_use, {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": "AUTHENTICATION_ERROR: The user needs to reconnect their account. Do NOT fabricate data. Tell the user to reconnect in Settings.",
                            "is_error": True,
                        }, "Authentication required - user needs to reconnect")

                    # Build content with image/PDF support
                    if image_blocks or pdf_blocks:
                        final_content = []
                        if result_text:
                            final_content.append({"type": "text", "text": result_text})
                        final_content.extend(image_blocks)
                        final_content.extend(pdf_blocks)
                        return (tool_use, {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": final_content,
                        }, None)

                    return (tool_use, {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    }, None)

                except Exception as e:
                    error_msg = _format_exception_message(e)
                    logger.error(f"Tool call failed: {error_msg}")
                    # Check if this is an auth error — use clear, structured message
                    if mcp_service._is_auth_error_message(error_msg):
                        return (tool_use, {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": "AUTHENTICATION_ERROR: The user needs to reconnect their account. Do NOT fabricate data. Tell the user to reconnect in Settings.",
                            "is_error": True,
                        }, "Authentication required - user needs to reconnect")
                    return (tool_use, {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"TOOL_ERROR: {error_msg}. Do NOT make up data. Report this error to the user.",
                        "is_error": True,
                    }, error_msg)

            if len(tool_use_blocks) > 1:
                logger.info(f"⚡ Executing {len(tool_use_blocks)} tools in PARALLEL")

            parallel_results = await asyncio.gather(*[execute_tool_stream(t) for t in tool_use_blocks])

            # Collect results and yield completion events
            # Truncate large results to speed up Claude's processing
            MAX_TOOL_RESULT_CHARS = 15000  # ~3750 tokens, plenty for summaries
            tool_results = []
            for tool_use, result_dict, error in parallel_results:
                content = result_dict.get('content', '')

                # Only truncate text content, not image/PDF list content
                if isinstance(content, str):
                    content_len = len(content)
                    if content_len > MAX_TOOL_RESULT_CHARS:
                        truncated_content = content[:MAX_TOOL_RESULT_CHARS] + f"\n\n[... truncated {content_len - MAX_TOOL_RESULT_CHARS} chars for speed ...]"
                        result_dict = {**result_dict, "content": truncated_content}
                        logger.info(f"📋 Tool result for {tool_use.name}: TRUNCATED {content_len} -> {MAX_TOOL_RESULT_CHARS} chars")
                    else:
                        logger.info(f"📋 Tool result for {tool_use.name}: {content_len} chars - {content[:200]}...")
                else:
                    # List content (images, PDFs) — log but don't truncate
                    logger.info(f"📋 Tool result for {tool_use.name}: {len(content)} content blocks (multimodal)")

                tool_results.append(result_dict)
                if error:
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": error}
                else:
                    yield {"type": "tool_end", "tool": tool_use.name, "success": True}

            # Filter out thinking blocks - only keep text and tool_use blocks for the conversation
            filtered_content = [
                block for block in final_message.content
                if not (hasattr(block, 'type') and block.type == 'thinking')
            ]
            logger.info(f"📨 Adding assistant message with {len(filtered_content)} blocks")
            logger.info(f"📨 Adding tool results: {len(tool_results)} results")
            messages.append({"role": "assistant", "content": filtered_content})
            messages.append({"role": "user", "content": tool_results})

            yield "\n"

        yield "\n\nI apologize, but I encountered an issue processing your request. Please try rephrasing your question."


# Global chat service instance
chat_service = ChatService()

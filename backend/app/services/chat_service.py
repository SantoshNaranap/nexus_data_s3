"""Chat service for handling LLM interactions."""

import logging
import asyncio
import time
from typing import List, Dict, Any, AsyncGenerator, Optional, Tuple
import json
import random
from concurrent.futures import ThreadPoolExecutor
from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock, MessageStreamEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.mcp_service import mcp_service
from app.models.database import ChatHistory
from anthropic import APIStatusError

logger = logging.getLogger(__name__)

# Thread pool for running synchronous Anthropic streaming in background
_stream_executor = ThreadPoolExecutor(max_workers=10)


def retry_on_overload(func, max_retries=3, base_delay=1.0):
    """
    Decorator/wrapper for retrying Claude API calls on overload errors.
    Uses exponential backoff with jitter.
    """
    def wrapper(*args, **kwargs):
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
        # All retries exhausted
        logger.error(f"Claude API still overloaded after {max_retries} retries")
        raise last_error or Exception("Claude API overloaded - please try again in a moment")
    return wrapper

# Performance tracking
PERF_METRICS = {
    "haiku_routing_time": [],
    "tool_execution_time": [],
    "sonnet_generation_time": [],
}


def get_quirky_thinking_message(tool_name: str) -> str:
    """Generate professional status messages based on tool name."""

    # Mapping of tool patterns to professional status messages
    status_messages = {
        "list": [
            "*Retrieving list...*",
            "*Fetching available items...*",
            "*Loading data...*",
        ],
        "read": [
            "*Reading content...*",
            "*Loading file contents...*",
            "*Retrieving document...*",
        ],
        "search": [
            "*Searching...*",
            "*Running search query...*",
            "*Finding matches...*",
        ],
        "get": [
            "*Fetching data...*",
            "*Retrieving information...*",
            "*Loading details...*",
        ],
        "create": [
            "*Creating new record...*",
            "*Processing creation request...*",
        ],
        "update": [
            "*Updating record...*",
            "*Applying changes...*",
        ],
        "delete": [
            "*Removing item...*",
            "*Processing deletion...*",
        ],
        "query": [
            "*Running query...*",
            "*Processing request...*",
            "*Analyzing data...*",
        ],
    }

    # Find matching pattern
    tool_lower = tool_name.lower()
    for pattern, messages in status_messages.items():
        if pattern in tool_lower:
            return random.choice(messages)

    # Default status messages if no pattern matches
    default_messages = [
        "*Processing...*",
        "*Working on it...*",
        "*Loading...*",
    ]

    return random.choice(default_messages)


class ChatService:
    """Service for handling chat interactions with Claude and MCP."""

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.sessions: Dict[str, List[dict]] = {}  # In-memory session storage for anonymous users

    async def save_chat_history(
        self,
        user_id: str,
        session_id: str,
        datasource: str,
        messages: List[dict],
        db: AsyncSession,
    ) -> None:
        """
        Save chat history to MySQL database for authenticated users.

        Args:
            user_id: User ID
            session_id: Session ID
            datasource: Datasource name
            messages: List of message dicts with 'role' and 'content'
            db: Database session
        """
        try:
            # Save each message (skip empty content to avoid Claude API errors)
            saved_count = 0
            for message in messages:
                content = message.get("content")
                # Skip empty messages - Claude API requires non-empty content
                if not content or not str(content).strip():
                    logger.debug(f"Skipping empty message with role: {message.get('role')}")
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
        """
        Get chat history from MySQL database for authenticated users.

        Args:
            user_id: User ID
            datasource: Datasource name
            session_id: Optional session ID to filter by
            db: Database session

        Returns:
            List of message dicts with 'role' and 'content'
        """
        if not db:
            return []

        try:
            # Build query
            query = select(ChatHistory).where(
                ChatHistory.user_id == user_id,
                ChatHistory.datasource == datasource,
            )

            if session_id:
                query = query.where(ChatHistory.session_id == session_id)

            # Order by creation time
            query = query.order_by(ChatHistory.created_at.asc())

            # Execute query
            result = await db.execute(query)
            chat_records = result.scalars().all()

            # Convert to dict format and filter out empty messages
            messages = []
            for record in chat_records:
                msg = record.to_dict()
                # Claude API requires all messages to have non-empty content
                if msg.get("content") and str(msg.get("content", "")).strip():
                    messages.append(msg)

            logger.info(f"Retrieved {len(messages)} messages from chat history for user {user_id[:8]}...")
            return messages

        except Exception as e:
            logger.error(f"Failed to get chat history: {str(e)}")
            return []

    async def _get_session_messages(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        datasource: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """
        Get messages for a session.

        For authenticated users: Load from MySQL database.
        For anonymous users: Load from in-memory storage.
        """
        if user_id and db and datasource:
            # Authenticated user - load from database
            messages = await self.get_chat_history(
                user_id=user_id,
                datasource=datasource,
                session_id=session_id,
                db=db,
            )
            return messages
        else:
            # Anonymous user - use in-memory storage
            if session_id not in self.sessions:
                self.sessions[session_id] = []
            return self.sessions[session_id]

    def _extract_bucket_name_from_messages(self, messages: List[dict]) -> str:
        """Extract S3 bucket name from user messages."""
        import re

        # Look through user messages for bucket names
        for message in reversed(messages):  # Start from most recent
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    # Common patterns for bucket names
                    # Match "bideclaudetest", "contents of bideclaudetest", etc.
                    patterns = [
                        r'\b(bideclaudetest)\b',
                        r'\b(bidebucket)\b',
                        r'bucket[:\s]+([a-z0-9\-]+)',
                        r'contents?\s+of\s+([a-z0-9\-]+)',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            bucket_name = match.group(1).lower()
                            return bucket_name

        return None

    def _extract_s3_key_from_messages(self, messages: List[dict]) -> str:
        """Extract S3 object key by finding it in previous list_objects results."""
        import re
        import json
        from urllib.parse import unquote_plus

        # First, get all available keys from previous list_objects/search_objects results
        available_keys = []
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                # Check if this is a tool result
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            try:
                                result_text = item.get("content", "")
                                if result_text:
                                    # Try to parse as JSON
                                    result_json = json.loads(result_text)
                                    if "objects" in result_json:
                                        for obj in result_json["objects"]:
                                            if "key" in obj:
                                                available_keys.append(obj["key"])
                            except:
                                pass

        logger.info(f"Available S3 keys from conversation (raw): {available_keys[:3]}...")  # Show first 3

        # URL-decode the keys for better matching
        decoded_keys = [(key, unquote_plus(key)) for key in available_keys]
        logger.info(f"Decoded keys (first 3): {[(k, d) for k, d in decoded_keys[:3]]}")

        # Now find the most recent user request mentioning a file
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    # Try to match file references in the user message
                    logger.info(f"Checking user message for file reference: {content[:200]}")
                    content_lower = content.lower()

                    # For each available key, see if it's mentioned in the user message
                    best_match = None
                    best_match_score = 0

                    for raw_key, decoded_key in decoded_keys:
                        # Work with the decoded version for matching
                        # Remove file extensions
                        decoded_base = decoded_key
                        for ext in ['.md', '.txt', '.pdf', '.docx', '.doc']:
                            decoded_base = decoded_base.replace(ext, '').replace(ext.upper(), '')

                        decoded_base_lower = decoded_base.lower()

                        # Normalize the key: remove spaces, special chars
                        key_normalized = re.sub(r'[^a-z0-9]', '', decoded_base_lower)

                        # Strategy 1: Direct substring match in original text
                        if decoded_base_lower in content_lower:
                            logger.info(f"✅ EXACT match! '{decoded_key}'")
                            return raw_key

                        # Strategy 2: Check if normalized key appears as substring in user message
                        content_normalized = re.sub(r'[^a-z0-9]', '', content_lower)
                        if key_normalized in content_normalized or content_normalized in key_normalized:
                            logger.info(f"✅ Normalized match! '{decoded_key}'")
                            return raw_key

                        # Strategy 3: Check for combined words (e.g., "nicecx" should match "nice cx")
                        # Remove all spaces from key to see if it appears in content
                        key_no_spaces = decoded_base_lower.replace(' ', '').replace('-', '')
                        if key_no_spaces in content_normalized:
                            logger.info(f"✅ Combined word match! '{decoded_key}' (as '{key_no_spaces}')")
                            return raw_key

                        # Also check if content (without spaces) appears in key
                        # This handles "nicecx" in content matching "nice cx agent flow" in key
                        for content_word in re.findall(r'\w+', content_lower):
                            if len(content_word) > 4:  # Only check substantial words
                                if content_word in key_no_spaces:
                                    logger.info(f"✅ Partial combined match! Found '{content_word}' in '{decoded_key}'")
                                    return raw_key

                        # Strategy 4: Word-based fuzzy matching with scoring
                        key_words = set(re.findall(r'\w+', decoded_base_lower))
                        key_words = {w for w in key_words if len(w) > 2}  # Filter out short words
                        content_words = set(re.findall(r'\w+', content_lower))
                        content_words = {w for w in content_words if len(w) > 2}
                        common_words = key_words & content_words

                        # Calculate match score based on common words
                        match_score = len(common_words)

                        # Boost score for longer/more distinctive words (words with more chars are more specific)
                        for word in common_words:
                            if len(word) > 5:  # Longer words are more distinctive
                                match_score += 1
                            if len(word) > 8:  # Very long words are very distinctive
                                match_score += 1

                        if match_score > best_match_score:
                            best_match = raw_key
                            best_match_score = match_score
                            logger.info(f"Candidate: '{decoded_key}' with score {match_score} (common words: {common_words})")

                    # If we found a fuzzy match, return it
                    if best_match and best_match_score >= 2:
                        logger.info(f"✅ Best match with score {best_match_score}: {best_match}")
                        return best_match

        # If only one key is available, use it
        if len(available_keys) == 1:
            logger.info(f"Only one key available, using it: {available_keys[0]}")
            return available_keys[0]

        logger.warning(f"Could not extract S3 key from messages. Had {len(available_keys)} keys available.")
        return None

    def _extract_table_name_from_messages(self, messages: List[dict]) -> str:
        """Extract MySQL table name from user messages."""
        import re

        # List of common words to exclude
        exclude_words = {
            'the', 'a', 'an', 'all', 'any', 'some', 'what', 'which', 'where',
            'when', 'how', 'about', 'that', 'this', 'these', 'those', 'common',
            'exist', 'structure', 'schema', 'database', 'table', 'column', 'row',
            'data', 'information', 'content', 'kind', 'type', 'direct', 'directly',
            'show', 'get', 'latest', 'first', 'last', 'recent', 'me', 'my'
        }

        # Look through user messages for table names
        for message in reversed(messages):  # Start from most recent
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    # Common patterns for table names - comprehensive list
                    patterns = [
                        # Explicit table patterns
                        r'from\s+(?:the\s+)?([a-z_][a-z0-9_]*)\s+table',
                        r'(?:describe|query)\s+(?:the\s+)?([a-z_][a-z0-9_]*)\s+table',
                        r'([a-z_][a-z0-9_]*)\s+table\s+(?:structure|schema)',
                        r'table\s+(?:called|named)\s+([a-z_][a-z0-9_]*)',
                        r'rows?\s+from\s+(?:the\s+)?([a-z_][a-z0-9_]*)',

                        # Natural language patterns
                        r'(?:latest|recent|first|last)\s+(?:\d+\s+)?([a-z_][a-z0-9_]*)',  # "latest users", "first 5 orders"
                        r'(?:show|get|list|display)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?([a-z_][a-z0-9_]*)',  # "show me users", "get all orders"
                        r'how\s+many\s+([a-z_][a-z0-9_]*)',  # "how many users"
                        r'count\s+(?:of\s+)?([a-z_][a-z0-9_]*)',  # "count of users"
                        r'(?:select|query)\s+(?:from\s+)?([a-z_][a-z0-9_]*)',  # "select from users"
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            table_name = match.group(1).lower()
                            # Filter out common words
                            if table_name not in exclude_words and len(table_name) > 2:
                                logger.info(f"Extracted table name: {table_name}")
                                return table_name

        return None

    def _extract_database_name_from_messages(self, messages: List[dict]) -> str:
        """Extract MySQL database name from user messages or use default."""
        import re

        # List of common words to exclude
        exclude_words = {
            'the', 'a', 'an', 'all', 'any', 'some', 'what', 'which', 'where',
            'when', 'how', 'about', 'that', 'this', 'these', 'those', 'common',
            'exist', 'structure', 'schema', 'database', 'table', 'column', 'row',
            'data', 'information', 'content', 'kind', 'type', 'direct', 'directly'
        }

        # Look through user messages for database names
        for message in reversed(messages):  # Start from most recent
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    # Common patterns for database names - more specific
                    patterns = [
                        r'(?:database|db)\s+(?:named|called)\s+([a-z_][a-z0-9_]*)',
                        r'([a-z_][a-z0-9_]*)\s+database',
                        r'in\s+(?:the\s+)?([a-z_][a-z0-9_]*)\s+database',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            db_name = match.group(1).lower()
                            # Filter out common words
                            if db_name not in exclude_words and len(db_name) > 2:
                                logger.info(f"Extracted database name: {db_name}")
                                return db_name

        # Use default from settings
        default_db = settings.mysql_database
        logger.info(f"No database name found, using default: {default_db}")
        return default_db

    def _construct_mysql_query_from_messages(self, messages: List[dict]) -> str:
        """Construct a SELECT query from natural language in user messages."""
        import re

        # Look through user messages for query intentions
        for message in reversed(messages):  # Start from most recent
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    content_lower = content.lower()

                    # Extract table name
                    table_name = self._extract_table_name_from_messages(messages)
                    if not table_name:
                        return None

                    # Extract LIMIT
                    limit = 100  # Default
                    limit_match = re.search(r'(\d+)\s+rows?', content_lower)
                    if limit_match:
                        limit = int(limit_match.group(1))
                    elif 'first' in content_lower or 'top' in content_lower:
                        num_match = re.search(r'(?:first|top)\s+(\d+)', content_lower)
                        if num_match:
                            limit = int(num_match.group(1))
                    elif 'latest' in content_lower or 'recent' in content_lower:
                        # Default to 10 for latest/recent queries
                        num_match = re.search(r'(?:latest|recent)\s+(\d+)', content_lower)
                        if num_match:
                            limit = int(num_match.group(1))
                        else:
                            limit = 10  # Default for "latest" queries

                    # Check if we need ORDER BY DESC for "latest" or "recent"
                    order_by = ""
                    if 'latest' in content_lower or 'recent' in content_lower or 'last' in content_lower:
                        # Try common column names for ordering
                        # Use table_name + _id pattern (e.g., users -> user_id)
                        # Fallback to created_at or id
                        possible_columns = [
                            f"{table_name.rstrip('s')}_id",  # users -> user_id, orders -> order_id
                            "id",
                            "created_at",
                            "updated_at"
                        ]
                        # Use the first one (table_name_id pattern is most common)
                        order_column = possible_columns[0]
                        order_by = f" ORDER BY {order_column} DESC"

                    # Construct query
                    query = f"SELECT * FROM {table_name}{order_by} LIMIT {limit}"
                    logger.info(f"Constructed query: {query}")
                    return query

        return None

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
        tools = await self._get_tools(datasource)

        # Create system prompt
        system_prompt = self._create_system_prompt(datasource)

        # TRY FAST PATH: Use direct routing for common queries
        fast_tools = await self._fast_tool_routing(message, tools, datasource)

        if fast_tools:
            # FAST PATH: Direct routing identified tools, execute in parallel
            logger.info(f"⚡ Using FAST PATH with {len(fast_tools)} tool(s): {[t['tool'] for t in fast_tools]}")

            # Execute tools in parallel
            tool_results = await self._execute_tools_parallel(
                fast_tools, datasource, credential_session_id, user_id, db
            )

            # Build context from tool results for Claude to generate response
            tool_context = "\n\n".join([
                f"Tool: {r['tool']}\nResult: {r.get('result', r.get('error', 'No result'))}"
                for r in tool_results
            ])

            # Add tool results to messages for context
            messages.append({
                "role": "assistant",
                "content": f"I retrieved the following data:\n{tool_context[:8000]}"
            })
            messages.append({
                "role": "user",
                "content": "Based on the data above, please provide a clear, well-formatted response to my original question."
            })

            # Use Claude just for response generation (no tools needed, with retry)
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
            tool_calls = [{"tool": t["tool"], "args": t["args"]} for t in fast_tools]
        else:
            # SLOW PATH: Process with Claude tool loop
            response_text, tool_calls = await self._call_claude(
                messages, tools, system_prompt, datasource, credential_session_id, user_id, db
            )

        # Add assistant message to history
        assistant_message = {"role": "assistant", "content": response_text}
        messages.append(assistant_message)

        # Save to database if authenticated user
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
                # Don't fail the request if saving fails

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

        # Check if user wants fresh data (bypass cache)
        force_refresh = mcp_service.should_force_refresh(message)
        if force_refresh:
            logger.info(f"🔄 User requested refresh - bypassing cache")

        # CHECK ULTRA-FAST PATH FIRST (skip Claude entirely for simple queries)
        if self._can_use_ultra_fast_path(message, datasource):
            logger.info(f"⚡⚡⚡ Attempting ULTRA-FAST PATH (no Claude API call)")

            # Get tool call directly
            direct_tools = self._direct_tool_routing(message, datasource)
            if direct_tools and len(direct_tools) == 1:
                tool_call = direct_tools[0]
                tool_name = tool_call["tool"]
                tool_args = tool_call.get("args", {})

                # Execute tool
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
                    formatted = self._format_ultra_fast_response(datasource, tool_name, result_text)
                    if formatted:
                        elapsed = time.time() - start_time
                        logger.info(f"⚡⚡⚡ ULTRA-FAST PATH success in {elapsed:.2f}s (no Claude!)")

                        # Stream the formatted response in word-sized chunks for smooth effect
                        import re
                        # Split by words while keeping punctuation and whitespace attached
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
                            try:
                                await self.save_chat_history(user_id, session_id, datasource, [user_message, assistant_message], db)
                            except Exception as e:
                                logger.error(f"Failed to save chat history: {str(e)}")

                        return  # Exit early - we're done!

                except Exception as e:
                    logger.warning(f"Ultra-fast path failed, falling back to regular path: {e}")

        # IMMEDIATE FEEDBACK - Send within 50ms
        immediate_feedback = self._get_immediate_feedback_message(datasource, message)
        thinking_summary = self._get_thinking_summary(datasource, message)
        # Send thinking event for the collapsible indicator
        yield {"type": "thinking", "content": thinking_summary}
        yield {"type": "text", "content": immediate_feedback + "\n\n"}
        logger.info(f"⚡ Immediate feedback sent in {(time.time() - start_time)*1000:.0f}ms")

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
        tools = await self._get_tools(datasource)

        # Create system prompt
        system_prompt = self._create_system_prompt(datasource)

        # TRY FAST PATH: Use Haiku for simple tool routing
        fast_tools = await self._fast_tool_routing(message, tools, datasource)

        if fast_tools:
            # FAST PATH: Haiku identified tools, execute in parallel
            logger.info(f"⚡ Using FAST PATH with {len(fast_tools)} tool(s)")
            yield "*Found relevant data...*\n\n"

            # Execute tools in parallel
            tool_results = await self._execute_tools_parallel(
                fast_tools, datasource, credential_session_id, user_id, db
            )

            # Build context from tool results for Sonnet to generate response
            tool_context = "\n\n".join([
                f"Tool: {r['tool']}\nResult: {r.get('result', r.get('error', 'No result'))}"
                for r in tool_results
            ])

            # Add tool results to messages for context
            messages.append({
                "role": "assistant",
                "content": f"I retrieved the following data:\n{tool_context[:2000]}"
            })
            messages.append({
                "role": "user",
                "content": "Based on the data above, please provide a clear, well-formatted response to my original question."
            })

            # Now use Sonnet just for response generation (no tools needed)
            generation_start = time.time()

            # Use async queue to bridge sync streaming to async for true streaming
            queue: asyncio.Queue = asyncio.Queue()

            def run_fast_stream():
                """Run sync stream in thread, put events in queue immediately."""
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
                                    # Put text in queue immediately
                                    queue.put_nowait({"type": "text", "content": event.delta.text})
                    queue.put_nowait(None)  # Signal completion
                except Exception as e:
                    logger.error(f"Fast stream error: {e}")
                    queue.put_nowait({"type": "error", "error": str(e)})
                    queue.put_nowait(None)

            # Start streaming in background thread
            loop = asyncio.get_event_loop()
            stream_task = loop.run_in_executor(_stream_executor, run_fast_stream)

            # Yield events as they arrive in the queue
            full_response = ""
            while True:
                try:
                    # Wait for events with timeout to avoid blocking forever
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                    if event is None:
                        break  # Stream complete
                    if event.get("type") == "text":
                        chunk = event["content"]
                        full_response += chunk
                        yield {"type": "text", "content": chunk}  # Yield as structured event
                    elif event.get("type") == "error":
                        yield {"type": "text", "content": f"\n\nError: {event['error']}"}
                        break
                except asyncio.TimeoutError:
                    logger.warning("Stream timeout in fast path")
                    break

            # Wait for background thread to complete
            await stream_task

            PERF_METRICS["sonnet_generation_time"].append(time.time() - generation_start)
            logger.info(f"⚡ FAST PATH total time: {time.time() - start_time:.2f}s")

        else:
            # STANDARD PATH: Complex query, use full Sonnet flow
            logger.info(f"📝 Using STANDARD PATH (complex query)")
            yield {"type": "thinking", "content": "🔄 *Analyzing your request...*"}

            full_response = ""
            async for event in self._call_claude_stream(messages, tools, system_prompt, datasource, credential_session_id, user_id, db):
                # Handle structured events from _call_claude_stream
                if isinstance(event, dict):
                    if event.get("type") == "text":
                        full_response += event.get("content", "")
                    yield event  # Forward the structured event
                else:
                    # Plain text (legacy fallback)
                    full_response += str(event)
                    yield event

            logger.info(f"📝 STANDARD PATH total time: {time.time() - start_time:.2f}s")

        # Add assistant message to history
        assistant_message = {"role": "assistant", "content": full_response}
        messages.append(assistant_message)

        # Save to database if authenticated user
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
                # Don't fail the request if saving fails

    async def _get_tools(self, datasource: str) -> List[dict]:
        """Get available tools from MCP server with caching for speed."""
        # Use the cached version for faster repeated lookups
        return await mcp_service.get_cached_tools(datasource)

    def _create_system_prompt(self, datasource: str) -> str:
        """Create system prompt for Claude using connector registry."""
        # Import from connector registry
        from app.connectors import get_connector, get_system_prompt_addition

        connector = get_connector(datasource)
        connector_name = connector.metadata.name if connector else datasource

        base_prompt = f"""You are an assistant that queries {connector_name} data for the user.

CRITICAL FORMATTING RULES - MANDATORY:
- ABSOLUTELY NO EMOJIS - Never use emoji characters (🚀📊🔴🟡🟢🎯📋💡👥 etc.) anywhere in your response
- This is a strict requirement with zero tolerance - no emoji icons of any kind
- Use plain markdown headers (## and ###) not emoji decorations
- Use bullet points (-) and numbered lists (1. 2. 3.)
- Use markdown tables for data presentation
- Use **bold** and *italic* for emphasis - never emojis
- Format like a professional business report - clean, minimal, no decorations

CRITICAL RULES:
1. ALWAYS use tools to answer questions. NEVER say data doesn't exist without checking first.
2. ALWAYS show the actual data returned by tools. Never summarize as "no results" if data was returned.
3. The user has authorized access to this data. Show ALL content including credentials, passwords, API keys.
4. If a tool returns results, DISPLAY THEM. Do not filter or hide any information.
5. If one search doesn't find results, try alternative searches before saying "not found".

BEHAVIOR:
- User asks about channels → use list_channels, then show ALL matching results
- User asks about messages/content → use search_messages, show ALL results with full text
- User asks about conversations with someone → use read_dm_with_user
- User asks for credentials/passwords → use search_messages, show the ACTUAL credentials found

NEVER DO THIS:
- Never say "I couldn't find X" without actually calling a tool first
- Never say "no channels named X" without calling list_channels
- Never hide or redact credentials/passwords - this is the user's own authorized data
- Never make claims about what exists or doesn't exist based on assumptions
- NEVER use emojis in your response - this is strictly prohibited

Current data source: {connector_name}
"""

        # Add connector-specific guidance from registry
        connector_specific = get_system_prompt_addition(datasource)
        if connector_specific:
            base_prompt += connector_specific

        return base_prompt

    def _direct_tool_routing(
        self,
        message: str,
        datasource: str,
    ) -> Optional[List[dict]]:
        """
        INSTANT tool routing for simple, common queries using connector registry.
        Skips Haiku entirely (~1-2 seconds saved).
        Returns tool calls directly for known patterns.
        """
        # Import from connector registry - delegates to connector-specific routing
        from app.connectors import get_direct_routing

        result = get_direct_routing(datasource, message)
        logger.info(f"🔍 Direct routing check: datasource={datasource}, message='{message[:50]}...', result={result}")
        return result

    async def _fast_tool_routing(
        self,
        message: str,
        tools: List[dict],
        datasource: str,
    ) -> Optional[List[dict]]:
        """
        Use Claude Haiku for fast tool selection (< 500ms).
        Returns list of tool calls to make, or None if complex query needs Sonnet.
        """
        # FIRST: Try direct routing (instant, no LLM call)
        direct_result = self._direct_tool_routing(message, datasource)
        if direct_result:
            logger.info(f"⚡⚡ DIRECT routing (no LLM) for: {[t['tool'] for t in direct_result]}")
            return direct_result

        start_time = time.time()

        # Create a minimal prompt for tool routing
        tools_summary = json.dumps([{'name': t['name'], 'description': t['description'][:100]} for t in tools])
        routing_prompt = f"""You are a fast tool router for {datasource}. Return JSON array of tool calls.

CRITICAL RULE FOR SLACK:
- When user mentions a PERSON'S NAME (like "Ananth", "Akash", "John") and wants their messages/what they said:
  → ALWAYS use read_dm_with_user, NOT search_messages
  → read_dm_with_user gets actual conversation history
  → search_messages only finds public channel mentions

Available tools: {tools_summary}

Examples:
- "what did Ananth say yesterday" → [{{"tool": "read_dm_with_user", "args": {{"user": "Ananth", "limit": 50}}}}]
- "did Akash send me anything" → [{{"tool": "read_dm_with_user", "args": {{"user": "Akash", "limit": 50}}}}]
- "messages from John" → [{{"tool": "read_dm_with_user", "args": {{"user": "John", "limit": 50}}}}]
- "conversations with Austin" → [{{"tool": "read_dm_with_user", "args": {{"user": "Austin", "limit": 50}}}}]
- "search for database credentials" → [{{"tool": "search_messages", "args": {{"query": "database credentials", "limit": 50}}}}]
- "find password" → [{{"tool": "search_messages", "args": {{"query": "password", "limit": 50}}}}]
- "list channels" → [{{"tool": "list_channels", "args": {{}}}}]

Return JSON array only, no explanations.
"""

        try:
            @retry_on_overload
            def haiku_routing():
                return self.client.messages.create(
                    model="claude-3-5-haiku-20241022",  # Fast model for routing
                    max_tokens=500,
                    system=routing_prompt,
                    messages=[{"role": "user", "content": message}],
                )
            response = haiku_routing()

            elapsed = time.time() - start_time
            PERF_METRICS["haiku_routing_time"].append(elapsed)
            logger.info(f"⚡ Haiku routing completed in {elapsed:.2f}s")

            # Parse response
            response_text = response.content[0].text if response.content else "[]"

            # Try to extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                tool_calls = json.loads(json_match.group())
                if tool_calls:
                    logger.info(f"⚡ Haiku routed to tools: {[t['tool'] for t in tool_calls]}")
                    return tool_calls

            return None  # Let Sonnet handle it

        except Exception as e:
            logger.warning(f"Fast routing failed, falling back to Sonnet: {e}")
            return None

    async def _execute_tools_parallel(
        self,
        tool_calls: List[dict],
        datasource: str,
        credential_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """
        Execute multiple tool calls in parallel for speed.
        """
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
        PERF_METRICS["tool_execution_time"].append(elapsed)
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

    def _can_use_ultra_fast_path(self, message: str, datasource: str) -> bool:
        """
        Check if we can use ultra-fast path (skip Claude entirely).
        Only for very simple, direct queries where we can format the response ourselves.
        """
        message_lower = message.lower().strip()

        # S3: List buckets - very simple response
        if datasource == "s3":
            if any(kw in message_lower for kw in ["bucket", "buckets", "what bucket"]):
                return True

        # JIRA: List projects - simple table response
        if datasource == "jira":
            if any(kw in message_lower for kw in ["project", "projects", "what project"]):
                return True

        return False

    def _format_ultra_fast_response(self, datasource: str, tool_name: str, result: str) -> str:
        """
        Format tool results directly without Claude (ultra-fast path).
        """
        import json

        try:
            data = json.loads(result)
        except:
            # Can't parse, fall back to regular path
            return None

        if datasource == "s3" and tool_name == "list_buckets":
            buckets = data.get("buckets", [])
            if not buckets:
                return "No S3 buckets found in your account."

            response = f"## 🪣 Your S3 Buckets ({len(buckets)} found)\n\n"
            response += "| Bucket Name | Created |\n"
            response += "|------------|--------|\n"
            for bucket in buckets:
                name = bucket.get("name", "Unknown")
                created = bucket.get("creation_date", "Unknown")[:10] if bucket.get("creation_date") else "Unknown"
                response += f"| {name} | {created} |\n"
            return response

        if datasource == "jira" and tool_name == "list_projects":
            projects = data.get("projects", [])
            if not projects:
                return "No JIRA projects found."

            response = f"## 📊 Your JIRA Projects ({len(projects)} found)\n\n"
            response += "| Key | Name | Type |\n"
            response += "|-----|------|------|\n"
            for proj in projects[:15]:  # Limit to first 15
                key = proj.get("key", "")
                name = proj.get("name", "")[:40]  # Truncate long names
                ptype = proj.get("type", proj.get("projectTypeKey", ""))
                response += f"| {key} | {name} | {ptype} |\n"

            if len(projects) > 15:
                response += f"\n*...and {len(projects) - 15} more projects*"
            return response

        return None  # Can't format, use regular path

    def _get_immediate_feedback_message(self, datasource: str, message: str) -> str:
        """Generate an immediate feedback message based on query type."""
        message_lower = message.lower()

        # Datasource-specific messages
        if datasource == "s3":
            if "bucket" in message_lower or "list" in message_lower:
                return "*Checking S3 buckets...*"
            elif "read" in message_lower or "content" in message_lower or "file" in message_lower:
                return "*Reading document...*"
            elif "search" in message_lower:
                return "*Searching documents...*"
            return "*Connecting to S3...*"

        elif datasource == "jira":
            if "project" in message_lower:
                return "*Fetching JIRA projects...*"
            elif "sprint" in message_lower:
                return "*Loading sprint data...*"
            elif "assign" in message_lower or "working" in message_lower or "who" in message_lower:
                return "*Checking team assignments...*"
            elif "backlog" in message_lower:
                return "*Analyzing backlog...*"
            return "*Querying JIRA...*"

        elif datasource == "mysql":
            if "table" in message_lower:
                return "*Listing tables...*"
            elif "schema" in message_lower or "structure" in message_lower:
                return "*Fetching schema...*"
            return "*Querying database...*"

        elif datasource == "google_workspace":
            if "calendar" in message_lower:
                return "*Checking calendar...*"
            elif "email" in message_lower or "gmail" in message_lower:
                return "*Loading emails...*"
            elif "doc" in message_lower or "sheet" in message_lower:
                return "*Fetching documents...*"
            return "*Connecting to Google Workspace...*"

        return "*Processing...*"

    def _get_thinking_summary(self, datasource: str, message: str) -> str:
        """Generate a thinking summary for the collapsible thinking indicator."""
        message_lower = message.lower()

        # Build a descriptive thinking message based on what we're doing
        thinking_parts = []

        # Add datasource context
        datasource_names = {
            "s3": "Amazon S3",
            "jira": "JIRA",
            "mysql": "MySQL database",
            "google_workspace": "Google Workspace",
            "slack": "Slack",
            "shopify": "Shopify",
        }
        ds_name = datasource_names.get(datasource, datasource)

        # Analyze query intent
        if any(kw in message_lower for kw in ["search", "find", "look for", "where"]):
            thinking_parts.append(f"Searching {ds_name} for relevant information")
        elif any(kw in message_lower for kw in ["list", "show", "get", "what"]):
            thinking_parts.append(f"Retrieving data from {ds_name}")
        elif any(kw in message_lower for kw in ["compare", "difference", "between"]):
            thinking_parts.append(f"Comparing information in {ds_name}")
        elif any(kw in message_lower for kw in ["similar", "apps", "market", "competitors"]):
            thinking_parts.append("Analyzing marketplace and competitive landscape")
        else:
            thinking_parts.append(f"Querying {ds_name}")

        return thinking_parts[0] if thinking_parts else f"Processing request for {ds_name}"

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
        """Call Claude API with tool support."""
        tool_calls_made = []
        max_iterations = 25  # Allow more iterations for complex queries

        for iteration in range(max_iterations):
            # Call Claude with retry on overload
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
            tool_results = []
            for tool_use in tool_use_blocks:
                # Auto-fix missing bucket parameter for S3 tools
                if datasource == "s3" and tool_use.name in ["list_objects", "read_object", "search_objects"]:
                    logger.info(f"S3 tool detected: {tool_use.name}, checking bucket parameter...")
                    if "bucket" not in tool_use.input or not tool_use.input.get("bucket"):
                        logger.info(f"Bucket parameter missing in {tool_use.name}, attempting auto-injection...")
                        logger.info(f"Messages for extraction: {[m.get('role') + ': ' + str(m.get('content'))[:100] for m in messages[-3:]]}")
                        # Extract bucket name from user messages
                        bucket_name = self._extract_bucket_name_from_messages(messages)
                        logger.info(f"Extracted bucket name: {bucket_name}")
                        if bucket_name:
                            tool_use.input["bucket"] = bucket_name
                            logger.info(f"✅ Auto-injected bucket parameter: {bucket_name}")
                        else:
                            logger.warning(f"⚠️ Failed to extract bucket name, using default: bideclaudetest")
                            tool_use.input["bucket"] = "bideclaudetest"
                    else:
                        logger.info(f"Bucket parameter already present: {tool_use.input.get('bucket')}")

                    # Auto-fix missing key parameter for read_object
                    if tool_use.name == "read_object":
                        if "key" not in tool_use.input or not tool_use.input.get("key"):
                            logger.info(f"Key parameter missing in read_object, attempting auto-extraction...")
                            # Extract key from conversation history
                            key = self._extract_s3_key_from_messages(messages)
                            logger.info(f"Extracted key: {key}")
                            if key:
                                tool_use.input["key"] = key
                                logger.info(f"✅ Auto-injected key parameter: {key}")
                            else:
                                logger.warning(f"⚠️ Failed to extract key from messages")
                        else:
                            logger.info(f"Key parameter already present: {tool_use.input.get('key')}")

                        logger.info(f"🔍 READ_OBJECT CALL - bucket: {tool_use.input.get('bucket')}, key: {tool_use.input.get('key')}")

                # Auto-fix missing parameters for MySQL tools
                if datasource == "mysql":
                    # Handle describe_table - needs table parameter
                    if tool_use.name == "describe_table":
                        if "table" not in tool_use.input or not tool_use.input.get("table"):
                            logger.info(f"Table parameter missing in describe_table, attempting auto-injection...")
                            table_name = self._extract_table_name_from_messages(messages)
                            if table_name:
                                tool_use.input["table"] = table_name
                                logger.info(f"✅ Auto-injected table parameter: {table_name}")
                            else:
                                logger.warning(f"⚠️ Failed to extract table name")

                    # Handle list_tables - needs database parameter
                    if tool_use.name == "list_tables":
                        if "database" not in tool_use.input or not tool_use.input.get("database"):
                            logger.info(f"Database parameter missing in list_tables, attempting auto-injection...")
                            db_name = self._extract_database_name_from_messages(messages)
                            if db_name:
                                tool_use.input["database"] = db_name
                                logger.info(f"✅ Auto-injected database parameter: {db_name}")

                    # Handle execute_query - needs query parameter
                    if tool_use.name == "execute_query":
                        if "query" not in tool_use.input or not tool_use.input.get("query"):
                            logger.info(f"Query parameter missing in execute_query, attempting auto-construction...")
                            query = self._construct_mysql_query_from_messages(messages)
                            if query:
                                tool_use.input["query"] = query
                                logger.info(f"✅ Auto-injected query parameter: {query}")
                            else:
                                logger.warning(f"⚠️ Failed to construct query")

                    # Handle get_table_stats - needs table parameter
                    if tool_use.name == "get_table_stats":
                        if "table" not in tool_use.input or not tool_use.input.get("table"):
                            logger.info(f"Table parameter missing in get_table_stats, attempting auto-injection...")
                            table_name = self._extract_table_name_from_messages(messages)
                            if table_name:
                                tool_use.input["table"] = table_name
                                logger.info(f"✅ Auto-injected table parameter: {table_name}")
                            else:
                                logger.warning(f"⚠️ Failed to extract table name")

                # Auto-inject user_google_email for Google Workspace tools
                if datasource == "google_workspace":
                    from app.core.config import settings
                    current_email = tool_use.input.get("user_google_email", "")
                    # Replace if missing, invalid, or placeholder
                    is_invalid = not current_email or "@" not in current_email or "placeholder" in current_email.lower()
                    if is_invalid and settings.user_google_email:
                        tool_use.input["user_google_email"] = settings.user_google_email
                        logger.info(f"✅ Auto-injected user_google_email: {settings.user_google_email} (replaced: {current_email})")
                    elif is_invalid:
                        logger.warning(f"⚠️ USER_GOOGLE_EMAIL not configured in settings")

                # Auto-fix missing parameters for JIRA tools
                if datasource == "jira":
                    # Handle query_jira - needs query parameter
                    if tool_use.name == "query_jira":
                        if "query" not in tool_use.input or not tool_use.input.get("query"):
                            logger.info(f"Query parameter missing in query_jira, attempting auto-injection...")
                            # Get the most recent user message
                            for msg in reversed(messages):
                                if msg.get("role") == "user":
                                    user_query = msg.get("content")
                                    if user_query and isinstance(user_query, str):
                                        tool_use.input["query"] = user_query
                                        logger.info(f"✅ Auto-injected query parameter from user message")
                                        break

                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
                    # Call the MCP tool
                    # Prioritize user_id over session_id for credentials
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

                except Exception as e:
                    logger.error(f"Tool call failed: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True,
                    })

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
        max_iterations = 25  # Increased to allow more attempts for complex queries

        for iteration in range(max_iterations):
            # Use async queue to bridge sync streaming to async for true streaming
            queue: asyncio.Queue = asyncio.Queue()
            final_message_holder = {"message": None}

            def run_claude_stream():
                """Run sync stream in thread, put events in queue immediately."""
                try:
                    # Extended thinking parameters
                    # Note: When using extended thinking with tools, we need to handle it carefully
                    stream_params = {
                        "model": "claude-sonnet-4-5-20250929",
                        "max_tokens": 16000,
                        "system": system_prompt,
                        "messages": messages,
                    }

                    # Add tools if available
                    if tools:
                        stream_params["tools"] = tools

                    # Enable extended thinking (works with Sonnet 4)
                    stream_params["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": 4000
                    }

                    stream = self.client.messages.stream(**stream_params)
                    with stream as event_stream:
                        current_block_type = None
                        for event in event_stream:
                            if event.type == "content_block_start":
                                # Track what type of block we're in
                                if hasattr(event.content_block, "type"):
                                    current_block_type = event.content_block.type
                                    if current_block_type == "thinking":
                                        # Signal start of thinking
                                        queue.put_nowait({"type": "thinking_start"})
                                    elif current_block_type == "tool_use":
                                        queue.put_nowait({"type": "tool_start", "block": event.content_block})
                            elif event.type == "content_block_delta":
                                if hasattr(event.delta, "thinking"):
                                    # Stream thinking content
                                    queue.put_nowait({"type": "thinking", "content": event.delta.thinking})
                                elif hasattr(event.delta, "text"):
                                    # Stream regular text content
                                    queue.put_nowait({"type": "text", "content": event.delta.text})
                            elif event.type == "content_block_stop":
                                if current_block_type == "thinking":
                                    # Signal end of thinking
                                    queue.put_nowait({"type": "thinking_end"})
                                current_block_type = None
                        # Get final message before exiting context
                        final_message_holder["message"] = event_stream.get_final_message()
                    queue.put_nowait(None)  # Signal completion
                except Exception as e:
                    logger.error(f"Stream error: {e}")
                    queue.put_nowait({"type": "error", "error": str(e)})
                    queue.put_nowait(None)

            # Start streaming in background thread
            loop = asyncio.get_event_loop()
            stream_task = loop.run_in_executor(_stream_executor, run_claude_stream)

            # Collect events as they arrive
            tool_use_blocks = []
            text_chunks = []
            thinking_chunks = []
            is_thinking = False

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120.0)
                    if event is None:
                        break  # Stream complete
                    event_type = event.get("type")

                    if event_type == "thinking_start":
                        is_thinking = True
                        yield {"type": "thinking_start"}
                    elif event_type == "thinking":
                        # Stream thinking content to frontend
                        thinking_chunks.append(event["content"])
                        yield {"type": "thinking", "content": event["content"]}
                    elif event_type == "thinking_end":
                        is_thinking = False
                        yield {"type": "thinking_end"}
                    elif event_type == "text":
                        text_chunks.append(event["content"])
                        yield {"type": "text", "content": event["content"]}
                    elif event_type == "tool_start":
                        tool_use_blocks.append(event["block"])
                    elif event_type == "error":
                        yield {"type": "text", "content": f"\n\nError: {event['error']}"}
                        break
                except asyncio.TimeoutError:
                    logger.warning("Stream timeout in _call_claude_stream")
                    break

            # Wait for background thread to complete
            await stream_task

            # Get the final message
            final_message = final_message_holder["message"]

            # Check for tool use
            if not tool_use_blocks and final_message:
                # Extract any tool use blocks from final message
                tool_use_blocks = [
                    block for block in final_message.content
                    if isinstance(block, ToolUseBlock)
                ]

            if not tool_use_blocks:
                # No tool calls, we're done
                return

            # Provide feedback about tool execution
            yield "\n\n"

            # Execute tool calls
            tool_results = []
            for i, tool_use in enumerate(tool_use_blocks):
                # Auto-fix missing bucket parameter for S3 tools
                if datasource == "s3" and tool_use.name in ["list_objects", "read_object", "search_objects"]:
                    logger.info(f"S3 tool detected: {tool_use.name}, checking bucket parameter...")
                    logger.info(f"Current tool_use.input: {tool_use.input}")
                    if "bucket" not in tool_use.input or not tool_use.input.get("bucket"):
                        logger.info(f"Bucket parameter missing in {tool_use.name}, attempting auto-injection...")
                        logger.info(f"Messages for extraction: {[m.get('role') + ': ' + str(m.get('content'))[:100] for m in messages[-3:]]}")
                        # Extract bucket name from user messages
                        bucket_name = self._extract_bucket_name_from_messages(messages)
                        logger.info(f"Extracted bucket name: {bucket_name}")
                        if bucket_name:
                            tool_use.input["bucket"] = bucket_name
                            logger.info(f"✅ Auto-injected bucket parameter: {bucket_name}")
                        else:
                            logger.warning(f"⚠️ Failed to extract bucket name, using default: bideclaudetest")
                            tool_use.input["bucket"] = "bideclaudetest"
                    else:
                        logger.info(f"Bucket parameter already present: {tool_use.input.get('bucket')}")

                    # Auto-fix missing key parameter for read_object
                    if tool_use.name == "read_object":
                        if "key" not in tool_use.input or not tool_use.input.get("key"):
                            logger.info(f"Key parameter missing in read_object, attempting auto-extraction...")
                            # Extract key from conversation history
                            key = self._extract_s3_key_from_messages(messages)
                            logger.info(f"Extracted key: {key}")
                            if key:
                                tool_use.input["key"] = key
                                logger.info(f"✅ Auto-injected key parameter: {key}")
                            else:
                                logger.warning(f"⚠️ Failed to extract key from messages")
                        else:
                            logger.info(f"Key parameter already present: {tool_use.input.get('key')}")

                        logger.info(f"🔍 READ_OBJECT CALL - bucket: {tool_use.input.get('bucket')}, key: {tool_use.input.get('key')}")

                # Auto-fix missing parameters for MySQL tools
                if datasource == "mysql":
                    # Handle describe_table - needs table parameter
                    if tool_use.name == "describe_table":
                        if "table" not in tool_use.input or not tool_use.input.get("table"):
                            logger.info(f"Table parameter missing in describe_table, attempting auto-injection...")
                            table_name = self._extract_table_name_from_messages(messages)
                            if table_name:
                                tool_use.input["table"] = table_name
                                logger.info(f"✅ Auto-injected table parameter: {table_name}")
                            else:
                                logger.warning(f"⚠️ Failed to extract table name")

                    # Handle list_tables - needs database parameter
                    if tool_use.name == "list_tables":
                        if "database" not in tool_use.input or not tool_use.input.get("database"):
                            logger.info(f"Database parameter missing in list_tables, attempting auto-injection...")
                            db_name = self._extract_database_name_from_messages(messages)
                            if db_name:
                                tool_use.input["database"] = db_name
                                logger.info(f"✅ Auto-injected database parameter: {db_name}")

                    # Handle execute_query - needs query parameter
                    if tool_use.name == "execute_query":
                        if "query" not in tool_use.input or not tool_use.input.get("query"):
                            logger.info(f"Query parameter missing in execute_query, attempting auto-construction...")
                            query = self._construct_mysql_query_from_messages(messages)
                            if query:
                                tool_use.input["query"] = query
                                logger.info(f"✅ Auto-injected query parameter: {query}")
                            else:
                                logger.warning(f"⚠️ Failed to construct query")

                    # Handle get_table_stats - needs table parameter
                    if tool_use.name == "get_table_stats":
                        if "table" not in tool_use.input or not tool_use.input.get("table"):
                            logger.info(f"Table parameter missing in get_table_stats, attempting auto-injection...")
                            table_name = self._extract_table_name_from_messages(messages)
                            if table_name:
                                tool_use.input["table"] = table_name
                                logger.info(f"✅ Auto-injected table parameter: {table_name}")
                            else:
                                logger.warning(f"⚠️ Failed to extract table name")

                # Auto-fix missing parameters for JIRA tools
                if datasource == "jira":
                    # Handle query_jira - needs query parameter
                    if tool_use.name == "query_jira":
                        if "query" not in tool_use.input or not tool_use.input.get("query"):
                            logger.info(f"Query parameter missing in query_jira, attempting auto-injection...")
                            # Get the most recent user message
                            for msg in reversed(messages):
                                if msg.get("role") == "user":
                                    user_query = msg.get("content")
                                    if user_query and isinstance(user_query, str):
                                        tool_use.input["query"] = user_query
                                        logger.info(f"✅ Auto-injected query parameter from user message")
                                        break

                # Send tool_start event with quirky message
                tool_feedback = get_quirky_thinking_message(tool_use.name)
                yield {"type": "tool_start", "tool": tool_use.name, "description": tool_feedback}

                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
                    # Call the MCP tool
                    # Prioritize user_id over session_id for credentials
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

                    # Send tool_end event
                    yield {"type": "tool_end", "tool": tool_use.name, "success": True}

                except Exception as e:
                    logger.error(f"Tool call failed: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True,
                    })
                    # Send tool_end event with error
                    yield {"type": "tool_end", "tool": tool_use.name, "success": False, "error": str(e)}

            # Add tool results to messages and continue
            messages.append({
                "role": "assistant",
                "content": final_message.content,
            })
            messages.append({
                "role": "user",
                "content": tool_results,
            })

            # Add a separator before the next response
            yield "\n"

        # Max iterations reached
        yield "\n\nI apologize, but I encountered an issue processing your request. Please try rephrasing your question."


# Global chat service instance
chat_service = ChatService()

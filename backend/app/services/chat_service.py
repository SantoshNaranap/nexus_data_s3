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

logger = logging.getLogger(__name__)

# Thread pool for running synchronous Anthropic streaming in background
_stream_executor = ThreadPoolExecutor(max_workers=10)

# Performance tracking
PERF_METRICS = {
    "haiku_routing_time": [],
    "tool_execution_time": [],
    "sonnet_generation_time": [],
}


def get_quirky_thinking_message(tool_name: str) -> str:
    """Generate fun, quirky thinking messages based on tool name."""

    # Mapping of tool patterns to quirky messages
    quirky_messages = {
        "list": [
            "🔍 *Rummaging through the digital filing cabinet...*",
            "📋 *Checking what's in the treasure chest...*",
            "🗂️ *Flipping through the catalog...*",
            "👀 *Taking a peek at what we've got...*",
        ],
        "read": [
            "📖 *Opening the scroll...*",
            "👓 *Adjusting my reading glasses...*",
            "📰 *Unfolding the ancient manuscript...*",
            "🔎 *Examining the contents closely...*",
        ],
        "search": [
            "🔍 *Channeling my inner detective...*",
            "🕵️ *On the hunt...*",
            "🎯 *Searching high and low...*",
            "🔎 *Following the breadcrumbs...*",
        ],
        "get": [
            "🎣 *Fetching that for you...*",
            "📦 *Retrieving from the vault...*",
            "🏃 *Running to get it...*",
            "🤲 *Grabbing that data...*",
        ],
        "create": [
            "✨ *Conjuring something new...*",
            "🎨 *Creating a masterpiece...*",
            "🔨 *Building that for you...*",
            "🪄 *Making magic happen...*",
        ],
        "update": [
            "✏️ *Making some tweaks...*",
            "🔧 *Fine-tuning this...*",
            "📝 *Updating the records...*",
            "🔄 *Applying the changes...*",
        ],
        "delete": [
            "🗑️ *To the trash it goes...*",
            "💥 *Removing that...*",
            "🧹 *Cleaning up...*",
            "👋 *Saying goodbye...*",
        ],
        "query": [
            "🤔 *Pondering this question...*",
            "💭 *Consulting the oracle...*",
            "🔮 *Peering into the database...*",
            "📊 *Crunching the numbers...*",
        ],
    }

    # Find matching pattern
    tool_lower = tool_name.lower()
    for pattern, messages in quirky_messages.items():
        if pattern in tool_lower:
            return random.choice(messages)

    # Default quirky messages if no pattern matches
    default_messages = [
        "🤖 *Processing...*",
        "⚙️ *Working on it...*",
        "💫 *Making it happen...*",
        "🎯 *On it...*",
        "✨ *Working some magic...*",
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
            # Save each message
            for message in messages:
                chat_record = ChatHistory(
                    user_id=user_id,
                    session_id=session_id,
                    datasource=datasource,
                    role=message.get("role"),
                    content=message.get("content"),
                )
                db.add(chat_record)

            await db.commit()
            logger.info(f"Saved {len(messages)} messages to chat history for user {user_id[:8]}...")

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

            # Convert to dict format
            messages = [record.to_dict() for record in chat_records]

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

        # Process with Claude
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
        yield immediate_feedback + "\n\n"
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
            yield "✓ Found relevant data...\n\n"

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
        """Create system prompt for Claude."""
        connector_info = mcp_service.connectors.get(datasource, {})
        connector_name = connector_info.get("name", datasource)

        base_prompt = f"""You are a helpful assistant that can query and interact with {connector_name}.

You have access to tools that allow you to interact with the {connector_name} data source.
When the user asks questions or requests actions, use the appropriate tools to fulfill their requests.

Always:
1. Use tools when needed to get accurate, up-to-date information
2. Provide clear, concise responses
3. Format data in a readable way (use tables, lists, etc. when appropriate)
4. If you encounter errors, explain them clearly to the user
5. Ask clarifying questions if the user's request is ambiguous
6. When interpreting dates from the data source, parse them carefully in ISO format (YYYY-MM-DD)
7. Present the actual data received from tools without making assumptions or adding interpretations about dates

Current data source: {connector_name}
"""

        # Add JIRA-specific guidance
        if datasource == "jira":
            base_prompt += """

JIRA-SPECIFIC GUIDELINES:

🎯 **RECOMMENDED: Use the query_jira tool for ALL user queries!**

The query_jira tool automatically handles:
- Name matching ("austin" → "Austin Prabu")
- Project name resolution ("Oralia-v2" → project key "ORALIA")
- Status filters ("open issues", "closed", "backlog")
- Count detection ("how many")
- JQL generation

**How to use query_jira:**
Simply pass the user's question directly to it:
- query_jira({"query": "What is austin working on in Oralia-v2?"})
- query_jira({"query": "How many open bugs are there?"})
- query_jira({"query": "Show me the backlog"})

**When to use other tools:**
Only use list_projects, get_project, search_issues, etc. when:
- User explicitly asks for ALL projects: use list_projects
- User asks for specific issue details by key: use get_issue
- You need to create/update issues: use create_issue, update_issue
- query_jira didn't return the expected results

**Response Format:**
- Always show the 'total' count from results
- Display issue keys, summaries, statuses, and assignees clearly
- For count queries, emphasize the number in your response
"""

        # Add S3-specific guidance
        if datasource == "s3":
            base_prompt += """

S3-SPECIFIC GUIDELINES:
1. **Always call list_buckets FIRST** to see available buckets in the AWS account
2. **Bucket parameter is REQUIRED** for most operations - never call list_objects, read_object, write_object, or search_objects without the bucket parameter
3. **Two-step workflow for listing contents:**
   - Step 1: Call list_buckets to get available bucket names
   - Step 2: Use the bucket name in list_objects: {"bucket": "bucket-name-here"}
4. **Three-step workflow for reading file contents:**
   - Step 1: Call list_objects to get the exact object keys
   - Step 2: Copy the EXACT "key" value from the list_objects response
   - Step 3: Call read_object with BOTH bucket AND the exact key: {"bucket": "bucket-name", "key": "exact-key-from-list"}
5. **CRITICAL for read_object:**
   - The "key" parameter must be the EXACT string from list_objects response
   - Do NOT modify the key (no URL encoding, no adding/removing slashes)
   - Example: If list_objects returns "key": "Chatbot Architecture Documentation.md", use EXACTLY that string
6. **Common user requests:**
   - "Show me the contents of [bucket-name]" → Call list_objects with {"bucket": "bucket-name-here"}
   - "What buckets do I have?" → Call list_buckets with {}
   - "Read file [name]" → First call list_objects to find the exact key, then read_object with exact key
7. **ALWAYS provide the bucket name** when calling any S3 tool except list_buckets
8. **When user mentions a specific bucket name**, use that exact name in the bucket parameter
"""

        # Add Google Workspace-specific guidance
        if datasource == "google_workspace":
            from app.core.config import settings
            email_info = f" (configured as: {settings.user_google_email})" if settings.user_google_email else ""
            base_prompt += f"""

GOOGLE WORKSPACE-SPECIFIC GUIDELINES:
1. **User email is pre-configured{email_info}** - DO NOT ask the user for their email address
2. **Directly call tools** when the user asks about their Google data (Docs, Sheets, Drive, Calendar, Gmail, etc.)
3. **Common user requests:**
   - "Show me my Google Docs" → Call search_drive_files with mimeType filter
   - "What's on my calendar?" → Call get_events
   - "Show my recent emails" → Call list_messages
   - "List my spreadsheets" → Call search_drive_files with Sheets mimeType
   - "What files are in Drive?" → Call search_drive_files
4. **OAuth Authorization:**
   - On first use, tools may require OAuth authorization
   - The system will automatically initiate the OAuth flow
   - Follow any authorization instructions provided by the tools
5. **Always use tools first** - don't ask for the email, just call the appropriate tool directly
"""

        return base_prompt

    def _direct_tool_routing(
        self,
        message: str,
        datasource: str,
    ) -> Optional[List[dict]]:
        """
        INSTANT tool routing for simple, common queries.
        Skips Haiku entirely (~1-2 seconds saved).
        Returns tool calls directly for known patterns.
        """
        message_lower = message.lower().strip()

        # S3 direct patterns
        if datasource == "s3":
            if any(kw in message_lower for kw in ["bucket", "buckets", "what bucket", "list bucket", "show bucket"]):
                return [{"tool": "list_buckets", "args": {}}]

        # JIRA direct patterns
        if datasource == "jira":
            if any(kw in message_lower for kw in ["project", "projects", "list project", "show project", "what project"]):
                return [{"tool": "list_projects", "args": {}}]

            # Any question about work/issues/tasks - use query_jira directly
            if any(kw in message_lower for kw in [
                "working on", "assigned", "issue", "task", "sprint", "backlog",
                "bug", "story", "ticket", "open", "closed", "status", "who"
            ]):
                return [{"tool": "query_jira", "args": {"query": message}}]

        # MySQL direct patterns
        if datasource == "mysql":
            if any(kw in message_lower for kw in ["table", "tables", "list table", "show table", "what table"]):
                return [{"tool": "list_tables", "args": {}}]

        # Google Workspace direct patterns
        if datasource == "google_workspace":
            if any(kw in message_lower for kw in ["calendar", "event", "meeting", "schedule"]):
                return [{"tool": "get_events", "args": {}}]
            if any(kw in message_lower for kw in ["email", "mail", "inbox", "gmail"]):
                return [{"tool": "list_messages", "args": {}}]
            if any(kw in message_lower for kw in ["drive", "file", "doc", "sheet", "document"]):
                return [{"tool": "search_drive_files", "args": {}}]

        return None  # Not a simple pattern, use Haiku or Sonnet

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
        routing_prompt = f"""You are a fast tool router. Given a user query and available tools, determine which tool(s) to call.

RULES:
1. Return ONLY tool calls, no explanations
2. If the query is simple and maps directly to a tool, return the tool call
3. If the query is complex or ambiguous, return empty (let the main model handle it)
4. For {datasource}, prefer the most direct tool

Available tools: {json.dumps([{'name': t['name'], 'description': t['description'][:100]} for t in tools])}

Respond with a JSON array of tool calls, or empty array [] if unsure.
Example: [{{"tool": "list_buckets", "args": {{}}}}]
"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Fast model for routing
                max_tokens=500,
                system=routing_prompt,
                messages=[{"role": "user", "content": message}],
            )

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
                return "🪣 *Checking your S3 buckets...*"
            elif "read" in message_lower or "content" in message_lower or "file" in message_lower:
                return "📄 *Reading document...*"
            elif "search" in message_lower:
                return "🔍 *Searching documents...*"
            return "☁️ *Connecting to S3...*"

        elif datasource == "jira":
            if "project" in message_lower:
                return "📊 *Fetching JIRA projects...*"
            elif "sprint" in message_lower:
                return "🏃 *Loading sprint data...*"
            elif "assign" in message_lower or "working" in message_lower or "who" in message_lower:
                return "👥 *Checking team assignments...*"
            elif "backlog" in message_lower:
                return "📋 *Analyzing backlog...*"
            return "🎫 *Querying JIRA...*"

        elif datasource == "mysql":
            if "table" in message_lower:
                return "📊 *Listing tables...*"
            elif "schema" in message_lower or "structure" in message_lower:
                return "🔧 *Fetching schema...*"
            return "🗄️ *Querying database...*"

        elif datasource == "google_workspace":
            if "calendar" in message_lower:
                return "📅 *Checking calendar...*"
            elif "email" in message_lower or "gmail" in message_lower:
                return "📧 *Loading emails...*"
            elif "doc" in message_lower or "sheet" in message_lower:
                return "📝 *Fetching documents...*"
            return "🔗 *Connecting to Google Workspace...*"

        return "⚡ *Processing...*"

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
        """Call Claude API with streaming and tool support - TRUE ASYNC STREAMING."""
        max_iterations = 25  # Increased to allow more attempts for complex queries

        for iteration in range(max_iterations):
            # Use async queue to bridge sync streaming to async for true streaming
            queue: asyncio.Queue = asyncio.Queue()
            final_message_holder = {"message": None}

            def run_claude_stream():
                """Run sync stream in thread, put events in queue immediately."""
                try:
                    stream = self.client.messages.stream(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                        tools=tools if tools else None,
                    )
                    with stream as event_stream:
                        for event in event_stream:
                            if event.type == "content_block_delta":
                                if hasattr(event.delta, "text"):
                                    # Put text in queue immediately for streaming
                                    queue.put_nowait({"type": "text", "content": event.delta.text})
                            elif event.type == "content_block_start":
                                if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                                    queue.put_nowait({"type": "tool_start", "block": event.content_block})
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

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120.0)
                    if event is None:
                        break  # Stream complete
                    if event.get("type") == "text":
                        text_chunks.append(event["content"])
                        yield {"type": "text", "content": event["content"]}  # Stream immediately as structured event!
                    elif event.get("type") == "tool_start":
                        tool_use_blocks.append(event["block"])
                    elif event.get("type") == "error":
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

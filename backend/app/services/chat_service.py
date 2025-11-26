"""Chat service for handling LLM interactions."""

import logging
from typing import List, Dict, Any, AsyncGenerator
import json
import random
from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock, MessageStreamEvent

from app.core.config import settings
from app.services.mcp_service import mcp_service

logger = logging.getLogger(__name__)


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
        self.sessions: Dict[str, List[dict]] = {}  # In-memory session storage

    def _get_session_messages(self, session_id: str) -> List[dict]:
        """Get messages for a session."""
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
        self, message: str, datasource: str, session_id: str
    ) -> tuple[str, List[dict]]:
        """Process a chat message using Claude and MCP tools."""
        # Get session history
        messages = self._get_session_messages(session_id)

        # Add user message to history
        messages.append({"role": "user", "content": message})

        # Get available tools from MCP server
        tools = await self._get_tools(datasource)

        # Create system prompt
        system_prompt = self._create_system_prompt(datasource)

        # Process with Claude
        response_text, tool_calls = await self._call_claude(
            messages, tools, system_prompt, datasource
        )

        # Add assistant message to history
        messages.append({"role": "assistant", "content": response_text})

        return response_text, tool_calls

    async def process_message_stream(
        self, message: str, datasource: str, session_id: str
    ) -> AsyncGenerator[str, None]:
        """Process a chat message with streaming response."""
        # Get session history
        messages = self._get_session_messages(session_id)

        # Add user message to history
        messages.append({"role": "user", "content": message})

        # Get available tools from MCP server
        tools = await self._get_tools(datasource)

        # Create system prompt
        system_prompt = self._create_system_prompt(datasource)

        # Process with streaming Claude - True character-by-character streaming like ChatGPT
        full_response = ""

        async for chunk in self._call_claude_stream(messages, tools, system_prompt, datasource):
            full_response += chunk
            # Send each character immediately for smooth ChatGPT-like streaming
            for char in chunk:
                yield char

        # Add assistant message to history
        messages.append({"role": "assistant", "content": full_response})

    async def _get_tools(self, datasource: str) -> List[dict]:
        """Get available tools from MCP server."""
        try:
            async with mcp_service.get_client(datasource) as session:
                tools_result = await session.list_tools()

                # Convert MCP tools to Claude format
                claude_tools = []
                for tool in tools_result.tools:
                    claude_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    })

                return claude_tools
        except Exception as e:
            logger.error(f"Failed to get tools for {datasource}: {str(e)}")
            return []

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
1. **Always call list_projects FIRST** when you don't know the project key
2. **JQL queries are REQUIRED** - never call search_issues with empty parameters
3. **Common queries for user questions:**
   - "How many open issues?" → Use JQL: 'status = Open' or 'status != Closed'
   - "Who is working on what?" → Use JQL: 'assignee is not EMPTY' (returns issues with assignees)
   - "Show me [person]'s work" → Use JQL: 'assignee = "[Full Name]"'
   - "What's the status of [project]?" → First list_projects, then use JQL: 'project = KEY'
4. **Two-step workflow:**
   - Step 1: Call list_projects to get available project keys
   - Step 2: Use the project key in your JQL query
5. **Count results** from the returned data - the 'total' field shows the count
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

    async def _call_claude(
        self,
        messages: List[dict],
        tools: List[dict],
        system_prompt: str,
        datasource: str,
    ) -> tuple[str, List[dict]]:
        """Call Claude API with tool support."""
        tool_calls_made = []
        max_iterations = 5  # Prevent infinite loops

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

                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
                    # Call the MCP tool
                    result = await mcp_service.call_tool(
                        datasource, tool_use.name, tool_use.input
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
    ) -> AsyncGenerator[str, None]:
        """Call Claude API with streaming and tool support."""
        max_iterations = 10  # Increased to allow more attempts for debugging

        for iteration in range(max_iterations):
            # Call Claude with streaming
            stream = self.client.messages.stream(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools if tools else None,
            )

            tool_use_blocks = []
            text_chunks = []

            with stream as event_stream:
                for event in event_stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            # Stream text chunks
                            text_chunks.append(event.delta.text)
                            yield event.delta.text
                    elif event.type == "content_block_start":
                        if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                            tool_use_blocks.append(event.content_block)

            # Get the final message
            final_message = event_stream.get_final_message()

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

                # Show tool execution feedback with quirky message
                tool_feedback = get_quirky_thinking_message(tool_use.name)
                yield tool_feedback

                logger.info(f"Claude calling tool: {tool_use.name} with args: {tool_use.input}")

                try:
                    result = await mcp_service.call_tool(
                        datasource, tool_use.name, tool_use.input
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

                    # Show completion
                    yield " ✓]\n"

                except Exception as e:
                    logger.error(f"Tool call failed: {str(e)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True,
                    })

                    # Show error
                    yield f" ✗ Error: {str(e)}]\n"

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

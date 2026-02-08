# ConnectorMCP: AI-Native Technical Specification

**Version:** 3.0  
**Date:** February 7, 2026  
**Goal:** Build a ChatGPT/Claude-like experience for enterprise data

---

## The Vision

Users type natural language → get accurate results. No regex, no keywords — pure AI understanding.

```
User: "What did John say yesterday?"
       ↓
   AI understands intent
       ↓
   AI selects right tool
       ↓
   AI extracts parameters
       ↓
   Returns accurate results
```

---

## Table of Contents

1. [Current Problems](#current-problems)
2. [The Fix](#the-fix-two-parts)
3. [Files to Change](#files-to-change)
4. [Implementation Details](#implementation-details)
5. [Implementation Order](#implementation-order)
6. [Testing](#testing)
7. [Official MCP Servers](#official-mcp-servers-evaluate-before-building)
8. [Expected Results](#expected-results)

---

## Current Problems

| Problem | Cause | Impact |
|---------|-------|--------|
| Inconsistent results | Too many overlapping tools | Same query → different answers |
| Slow responses | New connection per tool call | 3-10 seconds per query |
| Fragile parsing | Regex patterns | Breaks on query variations |

---

## The Fix: Two Parts

### Part 1: Reduce Complexity
- Consolidate overlapping tools (Slack: 19 → ~12, message tools: 5 → 2)
- Add connection pooling (reuse connections)

### Part 2: AI-Native Intelligence
- Use Haiku to select tools (not regex)
- Use Haiku to extract parameters (not regex)
- Use Haiku to classify query complexity (not regex)

---

## Files to Change

| File | Action | Priority |
|------|--------|----------|
| `backend/app/services/mcp_service.py` | ADD connection pooling | HIGH |
| `connectors/slack/src/slack_server.py` | CONSOLIDATE tools (5→2) | HIGH |
| `connectors/s3/src/s3_server.py` | CONSOLIDATE tools (2→1) | HIGH |
| `backend/app/services/tool_selector.py` | CREATE (new file) | HIGH |
| `backend/app/services/query_classifier.py` | DELETE | HIGH |
can| `backend/app/services/chat_service.py` | UPDATE (AI selector + reduce iterations + model selection) | HIGH |
| `connectors/jira/src/query_parser.py` | DELETE or SIMPLIFY | MEDIUM |
| `backend/app/core/prompts.py` | SIMPLIFY (remove conflicting instructions) | MEDIUM |

---

## Implementation Details

### 1. Connection Pooling

**File:** `backend/app/services/mcp_service.py`

**Problem:** Every tool call creates a new subprocess connection (200-500ms overhead).

**Fix:** Add connection pool to reuse connections.

```python
# Add after imports
from collections import defaultdict
from dataclasses import dataclass
import time

@dataclass
class PooledConnection:
    """A reusable MCP connection."""
    session: ClientSession
    read_stream: Any
    write_stream: Any
    created_at: float
    last_used: float
    datasource: str
    user_key: str


class MCPConnectionPool:
    """
    Reuses MCP connections instead of creating new ones.
    Saves 200-500ms per tool call.
    """
    
    def __init__(self, max_per_key: int = 3, idle_timeout: float = 300.0):
        self._pools: Dict[str, List[PooledConnection]] = defaultdict(list)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._max_per_key = max_per_key
        self._idle_timeout = idle_timeout
    
    async def get_connection(
        self,
        datasource: str,
        user_id: str = None,
        session_id: str = None,
        db = None,
        connector_env: dict = None,
    ) -> PooledConnection:
        """Get a connection from pool, or create new one."""
        pool_key = f"{datasource}:{user_id or session_id or 'default'}"
        
        async with self._locks[pool_key]:
            pool = self._pools[pool_key]
            now = time.time()
            
            # Try to get existing valid connection
            while pool:
                conn = pool.pop(0)
                if now - conn.last_used < self._idle_timeout:
                    conn.last_used = now
                    logger.info(f"♻️ Reusing connection for {pool_key}")
                    return conn
                else:
                    await self._close_connection(conn)
            
            # Create new connection
            logger.info(f"🆕 Creating new connection for {pool_key}")
            return await self._create_connection(datasource, user_id, session_id, db, connector_env, pool_key)
    
    async def return_connection(self, conn: PooledConnection):
        """Return connection to pool for reuse."""
        pool_key = f"{conn.datasource}:{conn.user_key}"
        
        async with self._locks[pool_key]:
            pool = self._pools[pool_key]
            if len(pool) < self._max_per_key:
                conn.last_used = time.time()
                pool.append(conn)
            else:
                await self._close_connection(conn)
    
    async def _create_connection(self, datasource, user_id, session_id, db, connector_env, pool_key):
        """Create a new MCP connection."""
        connector = get_connector(datasource)
        if not connector:
            raise ValueError(f"Unknown datasource: {datasource}")
        
        command, args = connector.get_server_command()
        final_env = {**os.environ.copy(), **(connector_env or {})}
        
        server = StdioServerParameters(command=command, args=args, env=final_env)
        read_stream, write_stream = await stdio_client(server).__aenter__()
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        
        now = time.time()
        return PooledConnection(
            session=session,
            read_stream=read_stream,
            write_stream=write_stream,
            created_at=now,
            last_used=now,
            datasource=datasource,
            user_key=user_id or session_id or "default",
        )
    
    async def _close_connection(self, conn: PooledConnection):
        """Close a connection."""
        try:
            await conn.session.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")


# Global pool instance
_connection_pool = MCPConnectionPool()
```

**Update `call_tool_fast()` to use the pool:**

```python
async def call_tool_fast(self, datasource, tool_name, arguments, user_id=None, session_id=None, db=None, force_refresh=False):
    """Tool call using connection pooling."""
    start = time.time()
    
    # Get environment
    connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)
    
    # Get pooled connection
    conn = await _connection_pool.get_connection(datasource, user_id, session_id, db, connector_env)
    
    try:
        result = await asyncio.wait_for(
            conn.session.call_tool(tool_name, arguments),
            timeout=MCP_TOOL_CALL_TIMEOUT
        )
        logger.info(f"⚡ {datasource}/{tool_name} in {(time.time()-start)*1000:.0f}ms")
        return result.content if result else []
    except Exception as e:
        await _connection_pool._close_connection(conn)
        conn = None
        raise
    finally:
        if conn:
            await _connection_pool.return_connection(conn)
```

---

### 2. Consolidate Slack Tools

**File:** `connectors/slack/src/slack_server.py`

**Problem:** 5+ tools for getting messages. Claude doesn't know which to pick.

**Fix:** Replace with 2 clear tools.

**Remove these tools from `@app.list_tools()`:**
- `read_messages`
- `search_messages`
- `get_all_recent_messages`
- `get_user_messages_in_channel`
- `get_all_user_messages`

**Add these tools instead:**

```python
Tool(
    name="find_messages",
    description="""Find Slack messages. Smart routing based on parameters.

USE THIS FOR ANY MESSAGE QUERY.

How it works:
- user only → gets all messages from that person
- channel only → reads that channel
- query only → searches by keyword
- user + channel → person's messages in that channel

Parameters:
- user (optional): Person's name
- channel (optional): Channel name
- query (optional): Search keyword
- hours_ago (optional): Time range, default 24
- limit (optional): Max results, default 50""",
    inputSchema={
        "type": "object",
        "properties": {
            "user": {"type": "string", "description": "Person's name"},
            "channel": {"type": "string", "description": "Channel name"},
            "query": {"type": "string", "description": "Search keyword"},
            "hours_ago": {"type": "integer", "default": 24},
            "limit": {"type": "integer", "default": 50},
        },
    }
),

Tool(
    name="get_slack_summary",
    description="""Get a summary of recent Slack activity.

USE THIS WHEN:
- "what did I miss"
- "catch me up"
- "summarize recent activity"

Parameters:
- hours_ago (optional): How far back, default 24""",
    inputSchema={
        "type": "object",
        "properties": {
            "hours_ago": {"type": "integer", "default": 24},
        },
    }
),
```

**Add routing in `@app.call_tool()`:**

```python
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    if name == "find_messages":
        user = arguments.get("user")
        channel = arguments.get("channel")
        query = arguments.get("query")
        hours_ago = arguments.get("hours_ago", 24)
        limit = arguments.get("limit", 50)
        
        # Route to appropriate internal function
        if user and not channel:
            return await handle_get_all_user_messages({"user": user, "hours_ago": hours_ago, "limit": limit})
        elif channel and not user:
            return await handle_read_messages({"channel": channel, "limit": limit})
        elif user and channel:
            return await handle_get_user_messages_in_channel({"user": user, "channel": channel, "limit": limit})
        elif query:
            return await handle_search_messages({"query": query, "limit": limit})
        else:
            return await handle_get_all_recent_messages({"hours_ago": hours_ago})
    
    elif name == "get_slack_summary":
        hours_ago = arguments.get("hours_ago", 24)
        return await handle_get_all_recent_messages({"hours_ago": hours_ago})
    
    # ... keep all other existing tool handlers unchanged ...
```

**Keep these tools unchanged:**
- `list_channels`, `get_channel_info`
- `send_message`, `send_dm`
- `list_users`, `get_user_info`, `get_user_presence`
- `get_thread_replies`, `add_reaction`
- `list_files`, `read_dm_with_user`, `list_dms`
- `search_in_dms`, `get_channel_activity`

---

### 3. Consolidate S3 Tools

**File:** `connectors/s3/src/s3_server.py`

**Problem:** `list_objects` and `search_objects` overlap.

**Fix:** Replace with one `find_objects` tool.

```python
Tool(
    name="find_objects",
    description="""Find objects in an S3 bucket.

USE THIS FOR ANY S3 FILE QUERY.

How it works:
- No filter → lists all objects
- prefix → filters by path (e.g., "logs/")
- pattern → filters by glob (e.g., "*.csv")
- Both → applies both filters

Parameters:
- bucket (required): Bucket name
- prefix (optional): Path prefix
- pattern (optional): Glob pattern (e.g., "*.json")
- max_keys (optional): Max results, default 100""",
    inputSchema={
        "type": "object",
        "properties": {
            "bucket": {"type": "string"},
            "prefix": {"type": "string"},
            "pattern": {"type": "string"},
            "max_keys": {"type": "integer", "default": 100},
        },
        "required": ["bucket"],
    }
),
```

**Routing:**

```python
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    if name == "find_objects":
        bucket = arguments["bucket"]
        prefix = arguments.get("prefix", "")
        pattern = arguments.get("pattern")
        max_keys = arguments.get("max_keys", 100)
        
        # Get objects
        objects = await _list_objects(bucket, prefix, max_keys)
        
        # Apply pattern filter
        if pattern:
            import fnmatch
            objects = [o for o in objects if fnmatch.fnmatch(o["key"], pattern)]
        
        return [TextContent(type="text", text=json.dumps(objects, indent=2))]
    
    # ... keep list_buckets, read_object, write_object unchanged ...
```

---

### 4. AI-Native Tool Selector (NEW FILE)

**File:** `backend/app/services/tool_selector.py`

This replaces all regex-based classification.

```python
"""
AI-Native Tool Selection

Uses Claude Haiku to:
1. Select the right tool for a query
2. Extract parameters from natural language
3. Classify query complexity

NO regex. NO keywords. Pure AI understanding.
"""

import logging
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from anthropic import Anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolSelection:
    """Result of AI tool selection."""
    selected_tools: List[dict]
    reasoning: str
    confidence: str  # "high", "medium", "low"


class AIToolSelector:
    """
    Uses Haiku to select the right tools for a query.
    
    Cost: ~$0.001 per selection (negligible)
    """
    
    MODEL = "claude-3-5-haiku-20241022"
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
    
    async def select_tools(
        self,
        query: str,
        datasource: str,
        available_tools: List[dict],
        max_tools: int = 3,
    ) -> ToolSelection:
        """Select the best tools for a query using AI."""
        
        # If few tools, skip selection
        if len(available_tools) <= max_tools:
            return ToolSelection(
                selected_tools=available_tools,
                reasoning="Few tools, using all",
                confidence="high"
            )
        
        # Format tools for prompt
        tool_list = []
        for i, tool in enumerate(available_tools, 1):
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")[:200]
            tool_list.append(f"{i}. {name}: {desc}")
        
        prompt = f"""Select the best tool(s) for this query.

Datasource: {datasource}
Query: "{query}"

Available tools:
{chr(10).join(tool_list)}

Return JSON: {{"tools": [1, 2], "reasoning": "why", "confidence": "high/medium/low"}}

Selection:"""

        try:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            
            text = response.content[0].text.strip()
            
            # Parse JSON from response
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(text[json_start:json_end])
                
                selected = []
                for idx in data.get("tools", []):
                    if 1 <= idx <= len(available_tools):
                        selected.append(available_tools[idx - 1])
                
                if selected:
                    names = [t.get("name") for t in selected]
                    logger.info(f"🎯 AI selected: {names}")
                    return ToolSelection(
                        selected_tools=selected,
                        reasoning=data.get("reasoning", ""),
                        confidence=data.get("confidence", "medium")
                    )
        
        except Exception as e:
            logger.warning(f"Tool selection failed: {e}")
        
        # Fallback: return all tools
        return ToolSelection(
            selected_tools=available_tools,
            reasoning="Selection failed, using all",
            confidence="low"
        )


class AIParameterExtractor:
    """
    Uses Haiku to extract parameters from natural language.
    
    Handles variations like:
    - "What did John say" → {user: "John"}
    - "John's messages" → {user: "John"}
    - "Messages from John" → {user: "John"}
    """
    
    MODEL = "claude-3-5-haiku-20241022"
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
    
    async def extract(self, query: str, tool_name: str, tool_schema: dict) -> dict:
        """Extract parameters for a tool from a query."""
        
        properties = tool_schema.get("properties", {})
        if not properties:
            return {}
        
        # Build parameter list
        param_list = []
        for name, schema in properties.items():
            desc = schema.get("description", "")
            param_list.append(f"- {name}: {desc}")
        
        prompt = f"""Extract parameters from this query for {tool_name}.

Query: "{query}"

Parameters to extract:
{chr(10).join(param_list)}

Return JSON with extracted values. Use null if not found.
Example: {{"user": "John", "hours_ago": 24}}

Extracted:"""

        try:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            
            text = response.content[0].text.strip()
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                params = json.loads(text[json_start:json_end])
                params = {k: v for k, v in params.items() if v is not None}
                logger.info(f"🎯 AI extracted: {params}")
                return params
        
        except Exception as e:
            logger.warning(f"Parameter extraction failed: {e}")
        
        return {}


class AIQueryClassifier:
    """
    Uses Haiku to classify if a query is simple or complex.
    
    Simple → use Haiku for execution (faster, cheaper)
    Complex → use Sonnet for execution (smarter)
    """
    
    MODEL = "claude-3-5-haiku-20241022"
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
    
    async def is_simple(self, query: str) -> bool:
        """Return True if query is simple (can use Haiku)."""
        
        prompt = f"""Is this query simple or complex?

Query: "{query}"

Simple = direct request, single step, no analysis
Complex = multi-step, needs reasoning, ambiguous

Return ONLY "simple" or "complex":"""

        try:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result = response.content[0].text.strip().lower()
            return "simple" in result
        
        except Exception as e:
            logger.warning(f"Classification failed: {e}")
            return False  # Default to complex (safer)


# Global instances
tool_selector = AIToolSelector()
parameter_extractor = AIParameterExtractor()
query_classifier = AIQueryClassifier()
```

---

### 5. Integrate AI Selector into Chat Service

**File:** `backend/app/services/chat_service.py`

**Add import:**
```python
from app.services.tool_selector import tool_selector, query_classifier
```

**Update `_get_tools()`:**
```python
async def _get_tools(self, datasource: str, query: str = "") -> List[dict]:
    """Get tools, optionally filtered by AI."""
    all_tools = await mcp_service.get_cached_tools(datasource)
    
    # Use AI to filter if many tools
    if query and len(all_tools) > 5:
        selection = await tool_selector.select_tools(
            query=query,
            datasource=datasource,
            available_tools=all_tools,
            max_tools=3,
        )
        logger.info(f"🎯 Filtered {len(all_tools)} → {len(selection.selected_tools)} tools")
        return selection.selected_tools
    
    return all_tools
```

**Update `_select_model()`:**
```python
async def _select_model(self, message: str) -> str:
    """Use AI to decide Haiku vs Sonnet."""
    if await query_classifier.is_simple(message):
        logger.info("Using HAIKU (simple query)")
        return "claude-3-5-haiku-20241022"
    else:
        logger.info("Using SONNET (complex query)")
        return "claude-sonnet-4-20250514"
```

**Update `process_message_stream()` to pass query:**
```python
async def process_message_stream(self, message: str, datasource: str, ...):
    # ...
    tools = await self._get_tools(datasource, query=message)  # Pass query
    # ...
```

---

### 6. Reduce Max Iterations

**File:** `backend/app/services/chat_service.py`

**Problem:** `max_iterations = 25` is excessive. Most queries need 2-4.

**Fix:** In `_call_claude()` method:

```python
# Change from:
max_iterations = 25

# To:
max_iterations = 10

# Also add early exit after the loop processes responses:
if not tool_use_blocks:
    # No tools called, we're done
    break
```

---

### 7. Simplify Prompts

**File:** `backend/app/core/prompts.py`

**Problem:** Conflicting instructions across datasources.

**Fix:** Remove tool selection hints (AI handles this now). Keep prompts simple:

```python
# Remove these conflicting instructions:
# - "ONE TOOL, ONE CALL" (Slack)
# - "ALWAYS call list_projects FIRST" (JIRA)
# - "YOU MUST PARSE" (S3)

# Replace with simple guidelines:
UNIVERSAL_RULES = """
- Use tools to get data, don't make things up
- If a tool fails, report the error clearly
- Quote results exactly as returned
- Don't fabricate data when results are empty
"""
```

---

### 8. Delete Old Files

**DELETE:** `backend/app/services/query_classifier.py`
- This file has regex patterns
- Replaced by AI-native `tool_selector.py`

**DELETE or SIMPLIFY:** `connectors/jira/src/query_parser.py`
- This file has regex patterns for JQL
- Let Claude extract JQL parameters naturally instead

---

## Implementation Order

### Week 0: Evaluate (Before Coding)
1. Test Atlassian's official JIRA server - compare to yours
2. Test AWS's official S3 server - compare to yours
3. Test Zencoder's Slack server - compare tool count
4. Decide: use official OR keep custom + apply fixes

### Week 1: Foundation
5. Add connection pooling to `mcp_service.py`
6. Consolidate Slack tools (5→2) — *if keeping custom*
7. Consolidate S3 tools (2→1) — *if keeping custom*
8. Reduce `max_iterations` to 10

### Week 2: AI-Native
9. Create `tool_selector.py`
10. DELETE `query_classifier.py`
11. Integrate AI selector into `chat_service.py`
12. DELETE/simplify `query_parser.py`
13. Simplify prompts in `prompts.py`

### Week 3: Polish
14. Test with query variations
15. Monitor Haiku costs
16. Tune prompts for edge cases

---

## Testing

Test that query variations all work correctly:

**Slack:**
```
"What did John say?" → find_messages(user="John")
"John's messages" → find_messages(user="John")
"Messages from John" → find_messages(user="John")
"Catch me up" → get_slack_summary()
"What did I miss?" → get_slack_summary()
"Messages in #general" → find_messages(channel="general")
```

**S3:**
```
"Files in my-bucket" → find_objects(bucket="my-bucket")
"CSV files in my-bucket" → find_objects(bucket="my-bucket", pattern="*.csv")
"What's in the logs folder?" → find_objects(bucket="...", prefix="logs/")
```

**JIRA:**
```
"Show me Oralia project" → search_issues (AI extracts project)
"Austin's tickets" → search_issues (AI extracts assignee)
"Open bugs" → search_issues (AI extracts status + type)
```

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Tool selection accuracy | ~50% | ~95% |
| Response time | 3-10s | 1-3s |
| Query variation handling | Fragile | Robust |
| Maintenance | High | Low |

---

## Cost

- Haiku tool selection: ~$0.001/query
- Haiku parameter extraction: ~$0.0005/query
- **Total added cost: ~$0.0015/query** (negligible)

---

---

## Official MCP Servers: Evaluate Before Building

Before implementing fixes, evaluate if official MCP servers would be better than custom ones.

### Comparison Table

| Your Connector | Official Alternative | Link | Recommendation |
|----------------|---------------------|------|----------------|
| **Slack** | Zencoder Slack Server | [GitHub](https://github.com/zencoderai/slack-mcp-server) | ⚠️ EVALUATE - community maintained |
| **JIRA** | Atlassian Official | [Atlassian](https://www.atlassian.com/platform/remote-mcp-server) | ⚠️ EVALUATE - official from Atlassian |
| **S3** | AWS Official | [GitHub](https://github.com/awslabs/mcp) | ⚠️ EVALUATE - official from AWS |
| **GitHub** | Archived Reference | [GitHub](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/github) | ✅ KEEP YOURS - official is basic |
| **MySQL** | None | N/A | ✅ KEEP YOURS - no alternative |
| **Google Workspace** | Google Drive only (archived) | N/A | ✅ KEEP YOURS - yours is more complete |
| **Shopify** | Shopify Dev Official | [GitHub](https://github.com/Shopify/dev-mcp) | ⚠️ EVALUATE |

### Evaluation Criteria

When comparing official vs custom:

| Criteria | Question to Ask |
|----------|-----------------|
| **Tool Count** | Does official have fewer, cleaner tools? |
| **Tool Design** | Are tools consolidated or overlapping? |
| **Auth Handling** | Does it handle OAuth properly? |
| **Maintenance** | Who maintains it? How often updated? |
| **Features** | Does it cover your use cases? |
| **Customization** | Can you extend it if needed? |

### Recommended Action

**Before implementing the fixes in this doc:**

1. **Test Atlassian's JIRA server**
   ```bash
   # Install and test
   npm install @anthropic/mcp-server-atlassian
   ```
   - If it has clean tool design → use it
   - If tools overlap or missing features → keep yours + apply fixes

2. **Test AWS S3 server**
   ```bash
   # From AWS MCP repo
   git clone https://github.com/awslabs/mcp
   ```
   - Check if it handles your S3 use cases
   - AWS maintains it, likely better auth

3. **Test Zencoder Slack server**
   ```bash
   git clone https://github.com/zencoderai/slack-mcp-server
   ```
   - Compare tool count to yours (you have 19)
   - If they consolidated tools → use theirs
   - If same problem → apply this doc's fixes to yours

### Decision Matrix

| If Official Server... | Then... |
|-----------------------|---------|
| Has fewer, cleaner tools | **USE OFFICIAL** |
| Has same overlapping tool problem | **KEEP YOURS + APPLY FIXES** |
| Missing features you need | **KEEP YOURS + APPLY FIXES** |
| Has better OAuth/auth | **USE OFFICIAL** |
| Poorly maintained (no updates) | **KEEP YOURS** |

### Keep Your Custom For:

- **MySQL** - No official alternative
- **Google Workspace** - Your implementation is comprehensive (Calendar, Docs, Sheets, Slides, Gmail, Drive, Forms, Tasks, Chat, Search)
- **Any connector with custom business logic**

### Why This Matters

Official servers are:
- Maintained by companies/community
- Follow MCP best practices
- Less likely to have the overlapping tool problem
- Handle auth edge cases

But your custom servers:
- Are tailored to your needs
- Give you full control
- Can have features officials don't

**The AI-native fixes in this doc apply to ANY MCP server** - official or custom. If you switch to official servers, you still benefit from:
- Connection pooling
- AI tool selection
- Reduced iterations

---

## Summary

**What to do:**

1. **Evaluate official servers** (JIRA, S3, Slack, Shopify)
2. Add connection pooling
3. Consolidate overlapping tools (if keeping custom)
4. Create AI-native `tool_selector.py`
5. Delete regex-based files
6. Integrate and test

**Result:** ChatGPT-like experience for enterprise data.

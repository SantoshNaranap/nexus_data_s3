"""
Tool Routing Service - Handles intelligent tool selection and routing.

This service provides multiple tiers of tool routing:
1. Direct routing - Pattern matching for common queries (instant, no LLM)
2. Fast routing - Haiku-based routing for simple queries (~500ms)
3. Standard routing - Full Sonnet flow for complex queries

Separating this logic allows for easy tuning of routing patterns without
touching the core chat flow.
"""

import logging
import time
import json
import re
from typing import List, Dict, Any, Optional

from anthropic import APIError, APIConnectionError, RateLimitError

from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)

# Performance tracking
ROUTING_METRICS = {
    "direct_routing_count": 0,
    "haiku_routing_time": [],
    "haiku_routing_count": 0,
}


class ToolRoutingService:
    """
    Intelligent tool routing for chat queries.

    Provides tiered routing to minimize latency:
    - Direct: ~0ms (pattern matching)
    - Haiku: ~300-500ms (fast LLM)
    - Sonnet: ~1-2s (full LLM with tools)
    """

    def __init__(self):
        self.client = claude_client.client

        # Direct routing patterns per datasource
        self._direct_patterns = self._build_direct_patterns()

    def _build_direct_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build pattern matchers for direct (instant) routing.

        Each pattern has:
        - keywords: list of keywords to match
        - tool: the tool to call
        - args: default arguments
        """
        return {
            "s3": [
                {
                    "keywords": ["bucket", "buckets", "what bucket", "list bucket", "show bucket"],
                    "tool": "list_buckets",
                    "args": {},
                },
            ],
            "jira": [
                {
                    # Only match explicit project listing requests
                    "keywords": ["list projects", "show projects", "what projects", "my projects"],
                    "tool": "list_projects",
                    "args": {},
                },
                {
                    # All other JIRA queries go through natural language
                    # Include common issue-related keywords
                    "keywords": ["working on", "assigned to", "issues in", "tasks in", "sprint", "backlog",
                                "bugs in", "stories in", "tickets in", "open issue", "closed issue",
                                "issue", "issues", "task", "tasks", "bug", "bugs", "story", "stories",
                                "ticket", "tickets", "what is", "tell me", "show me", "oralia", "status"],
                    "tool": "query_jira",
                    "args": {},
                    "args_from_message": True,  # Use message as query
                },
            ],
            "mysql": [
                {
                    # Only match explicit table listing requests
                    "keywords": ["list tables", "show tables", "what tables", "database schema"],
                    "tool": "list_tables",
                    "args": {},
                },
            ],
            "google_workspace": [
                {
                    "keywords": ["calendar", "event", "meeting", "schedule"],
                    "tool": "get_events",
                    "args": {},
                },
                {
                    "keywords": ["email", "mail", "inbox", "gmail"],
                    "tool": "list_messages",
                    "args": {},
                },
                {
                    "keywords": ["drive", "file", "doc", "sheet", "document"],
                    "tool": "search_drive_files",
                    "args": {},
                },
            ],
            "shopify": [
                {
                    "keywords": ["order", "orders", "recent order"],
                    "tool": "list_orders",
                    "args": {},
                },
                {
                    "keywords": ["product", "products", "inventory"],
                    "tool": "list_products",
                    "args": {},
                },
            ],
            "slack": [
                {
                    # Only match explicit channel listing requests
                    "keywords": ["list channels", "show channels", "what channels", "my channels"],
                    "tool": "list_channels",
                    "args": {},
                },
                {
                    # Only match explicit user listing requests
                    "keywords": ["list users", "show users", "team members", "who is on"],
                    "tool": "list_users",
                    "args": {},
                },
                {
                    # Match catch-up and recent activity requests
                    "keywords": ["what did i miss", "catch up", "recent activity", "what's happening"],
                    "tool": "get_all_recent_messages",
                    "args": {},
                    "args_from_message": True,
                },
                {
                    "keywords": ["search", "find", "look for"],
                    "tool": "search_messages",
                    "args": {},
                    "args_from_message": True,
                },
            ],
            "github": [
                {
                    "keywords": ["repo", "repos", "repository", "repositories", "my repos", "list repo"],
                    "tool": "list_repositories",
                    "args": {},
                },
                {
                    "keywords": ["issue", "issues", "bug", "bugs", "open issue", "list issue"],
                    "tool": "list_issues",
                    "args": {},
                    "args_from_message": True,
                },
                {
                    "keywords": ["pr", "prs", "pull request", "pull requests", "merge request"],
                    "tool": "list_pull_requests",
                    "args": {},
                    "args_from_message": True,
                },
                {
                    "keywords": ["commit", "commits", "recent commit", "latest commit"],
                    "tool": "list_commits",
                    "args": {},
                    "args_from_message": True,
                },
                {
                    "keywords": ["branch", "branches", "list branch"],
                    "tool": "list_branches",
                    "args": {},
                    "args_from_message": True,
                },
                {
                    "keywords": ["workflow", "action", "actions", "ci", "cd", "pipeline", "build"],
                    "tool": "get_workflow_runs",
                    "args": {},
                    "args_from_message": True,
                },
            ],
        }

    def direct_route(self, message: str, datasource: str) -> Optional[List[Dict[str, Any]]]:
        """
        Attempt direct (instant) routing based on keyword patterns.

        Args:
            message: User message
            datasource: Active datasource

        Returns:
            List of tool calls if pattern matched, None otherwise
        """
        message_lower = message.lower().strip()
        patterns = self._direct_patterns.get(datasource, [])

        for pattern in patterns:
            if any(kw in message_lower for kw in pattern["keywords"]):
                args = pattern.get("args", {}).copy()

                # Some tools need the message as an argument
                if pattern.get("args_from_message"):
                    args["query"] = message

                ROUTING_METRICS["direct_routing_count"] += 1
                logger.info(f"⚡⚡ DIRECT routing to {pattern['tool']}")

                return [{"tool": pattern["tool"], "args": args}]

        return None

    async def fast_route(
        self,
        message: str,
        tools: List[Dict[str, Any]],
        datasource: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Use Claude Haiku for fast tool selection (~500ms).

        Falls back to None if routing is ambiguous, letting Sonnet handle it.

        Args:
            message: User message
            tools: Available tools
            datasource: Active datasource

        Returns:
            List of tool calls if routing succeeded, None otherwise
        """
        # Try direct routing first (instant)
        direct_result = self.direct_route(message, datasource)
        if direct_result:
            return direct_result

        start_time = time.time()

        # Build minimal routing prompt with datasource-specific rules
        mysql_rules = ""
        schema_info = ""
        if datasource == "mysql":
            # Get cached schemas from mcp_service
            from app.services.mcp_service import mcp_service
            cached_schemas = mcp_service.get_all_cached_schemas()
            if cached_schemas:
                schema_lines = []
                for table, schema in cached_schemas.items():
                    # Extract just column names for brevity
                    schema_lines.append(f"- {table}: {schema[:200]}")
                schema_info = "\n".join(schema_lines[:10])  # Limit to 10 tables

            # Note: We now let Haiku handle complex MySQL queries since we've provided
            # good examples in the prompt. It can construct SQL without needing cached schemas.

            mysql_rules = f"""
MYSQL-SPECIFIC RULES:
- For queries about data, use execute_query with a proper SQL query
- IMPORTANT: ALWAYS provide the full SQL query in the args
- For "how many" or "count" or "number of" -> use SELECT COUNT(*)
- For "by type" or "each type" -> use GROUP BY
- For JOINs, use table.column syntax

MYSQL EXAMPLES:
- "number of providers" -> [{{"tool": "execute_query", "args": {{"query": "SELECT COUNT(*) as total FROM providers"}}}}]
- "providers by type" -> [{{"tool": "execute_query", "args": {{"query": "SELECT type, COUNT(*) as count FROM providers GROUP BY type"}}}}]
- "claims per provider type" -> [{{"tool": "execute_query", "args": {{"query": "SELECT p.type, COUNT(c.id) as claims FROM providers p LEFT JOIN claims c ON p.id = c.provider_id GROUP BY p.type"}}}}]
- "number of providers, providers by type, claims by provider type" -> Return MULTIPLE tool calls:
  [{{"tool": "execute_query", "args": {{"query": "SELECT COUNT(*) as total FROM providers"}}}},
   {{"tool": "execute_query", "args": {{"query": "SELECT type, COUNT(*) FROM providers GROUP BY type"}}}},
   {{"tool": "execute_query", "args": {{"query": "SELECT p.type, COUNT(c.id) FROM providers p LEFT JOIN claims c ON p.id = c.provider_id GROUP BY p.type"}}}}]

KNOWN TABLES: {list(cached_schemas.keys()) if cached_schemas else "providers, claims (assumed)"}
"""

        routing_prompt = f"""You are a fast tool router. Given a user query and available tools, determine which tool(s) to call.

PARAMETER EXTRACTION - CRITICAL:
- Extract parameter values that are explicitly mentioned in the user query
- For user/person names: Extract the name mentioned (e.g., "messages from John" -> user: "John")
- For time periods: Extract hours/days mentioned (e.g., "last 24 hours" -> hours_ago: 24)
- For channels: Extract channel names mentioned (e.g., "in #general" -> channel: "general")
- DO NOT fabricate values that are not in the query
- If a required parameter is truly missing, return empty array []

ROUTING RULES:
1. Return ONLY tool calls as JSON, no explanations
2. If the query mentions a person's name and asks for their messages, use get_all_user_messages with their name
3. If the query is complex or ambiguous, return empty [] (let the main model handle it)
4. For {datasource}, prefer the most direct tool
{mysql_rules}
Available tools: {json.dumps([{"name": t["name"], "description": t["description"][:100]} for t in tools])}

Respond with a JSON array of tool calls, or empty array [] if unsure.
Examples:
- "Get messages from John" -> [{{"tool": "get_all_user_messages", "args": {{"user": "John"}}}}]
- "List buckets" -> [{{"tool": "list_buckets", "args": {{}}}}]
"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=500,
                system=routing_prompt,
                messages=[{"role": "user", "content": message}],
            )

            elapsed = time.time() - start_time
            ROUTING_METRICS["haiku_routing_time"].append(elapsed)
            ROUTING_METRICS["haiku_routing_count"] += 1
            logger.info(f"⚡ Haiku routing completed in {elapsed:.2f}s")

            # Parse response
            response_text = response.content[0].text if response.content else "[]"
            logger.debug(f"Haiku raw response: {response_text[:500]}")

            # Extract JSON array from response - use non-greedy match to get first array
            # Also handle nested arrays by counting brackets
            json_match = re.search(r'\[', response_text)
            if json_match:
                start_idx = json_match.start()
                # Find the matching closing bracket
                bracket_count = 0
                end_idx = start_idx
                for i, char in enumerate(response_text[start_idx:], start_idx):
                    if char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end_idx = i + 1
                            break

                json_str = response_text[start_idx:end_idx]
                try:
                    tool_calls = json.loads(json_str)
                    if tool_calls and isinstance(tool_calls, list):
                        logger.info(f"⚡ Haiku routed to tools: {[t.get('tool', t.get('name', 'unknown')) for t in tool_calls]}")
                        return tool_calls
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse Haiku JSON: {e}, json_str={json_str[:200]}")

            return None  # Let Sonnet handle it

        except (APIError, APIConnectionError, RateLimitError) as e:
            logger.warning(f"Fast routing API error, falling back to Sonnet: {e}")
            return None
        except Exception as e:
            logger.warning(f"Fast routing unexpected error, falling back to Sonnet: {e}")
            return None

    def can_use_ultra_fast_path(self, message: str, datasource: str) -> bool:
        """
        Check if a query can use the ultra-fast path (skip Claude entirely).

        Ultra-fast path is used for very simple queries where:
        1. Direct routing can identify the tool
        2. Response can be formatted without LLM

        Args:
            message: User message
            datasource: Active datasource

        Returns:
            True if ultra-fast path is possible
        """
        # Check if direct routing would work
        result = self.direct_route(message, datasource)
        if not result:
            return False

        # Only certain tools support ultra-fast response formatting
        ultra_fast_tools = {
            "s3": ["list_buckets"],
            "jira": ["list_projects"],
            "mysql": ["list_tables"],
            "google_workspace": ["get_events", "list_messages", "search_drive_files"],
            "shopify": ["list_orders", "list_products"],
            "slack": ["list_channels", "list_users"],
            "github": ["list_repositories"],
        }

        tool_name = result[0]["tool"]
        supported_tools = ultra_fast_tools.get(datasource, [])

        return tool_name in supported_tools

    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing performance statistics."""
        haiku_times = ROUTING_METRICS["haiku_routing_time"]
        return {
            "direct_routing_count": ROUTING_METRICS["direct_routing_count"],
            "haiku_routing_count": ROUTING_METRICS["haiku_routing_count"],
            "haiku_avg_time_ms": (sum(haiku_times) / len(haiku_times) * 1000) if haiku_times else 0,
            "haiku_p95_time_ms": (sorted(haiku_times)[int(len(haiku_times) * 0.95)] * 1000) if len(haiku_times) > 20 else 0,
        }


# Global instance for import
tool_routing_service = ToolRoutingService()

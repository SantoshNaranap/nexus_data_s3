"""
Parameter Injection Service - Auto-fixes missing tool parameters.

This service handles the automatic injection of missing parameters for tool calls.
It extracts values from conversation context when Claude doesn't provide them.

Previously, this logic was duplicated between _call_claude and _call_claude_stream
in chat_service.py. Centralizing it here ensures:
1. DRY code - single place to update parameter injection logic
2. Easier testing - can unit test parameter extraction
3. Maintainability - datasource-specific logic is isolated

CONVERSATION CONTEXT FEATURE:
This service also maintains conversation context across messages, so follow-up
questions like "what else?" or "show more" understand the context from previous
messages (e.g., which bucket, project, or table was being discussed).
"""

import logging
import re
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.services.parameter_extractor import parameter_extractor

logger = logging.getLogger(__name__)


# =============================================================================
# GENERIC CONTEXT EXTRACTION PATTERNS
# =============================================================================
# These patterns are used to extract context from conversation history
# when a follow-up query doesn't explicitly mention the resource.

CONTEXT_PATTERNS = {
    "s3": {
        "bucket": [
            r"bucket[s]?\s+['\"]?(\w[\w\-\.]+\w)['\"]?",
            r"['\"](\w[\w\-\.]+\w)['\"]?\s+bucket",
            r"in\s+(\w[\w\-\.]+\w)\s+bucket",
            r"from\s+(\w[\w\-\.]+\w)\s+bucket",
            r"bidebucket|bideclaudetest",  # Known bucket names
        ],
        "key": [
            r"file[s]?\s+['\"]?([^\s'\"]+\.\w+)['\"]?",
            r"object[s]?\s+['\"]?([^\s'\"]+)['\"]?",
            r"key[s]?\s+['\"]?([^\s'\"]+)['\"]?",
        ],
    },
    "jira": {
        "project": [
            r"(oralia[-_\s]?v?\d*)",
            r"(zupain)",
            r"project\s+['\"]?(\w+[-_]?\w*)['\"]?",
            r"\b([A-Z]{2,10})-\d+\b",  # Extract project from issue key
        ],
    },
    "mysql": {
        "database": [
            # More specific patterns that require explicit database naming
            r"use\s+database\s+['\"]?(\w{4,})['\"]?",
            r"connect\s+to\s+['\"]?(\w{4,})['\"]?\s+database",
            r"database\s+named?\s+['\"]?(\w{4,})['\"]?",
            # Don't match generic words like "the" from conversational text
        ],
        "table": [
            r"table\s+['\"]?(\w+)['\"]?",
            r"from\s+['\"]?(\w+)['\"]?\s+table",
            r"in\s+['\"]?(\w+)['\"]?\s+table",
        ],
    },
    "google_workspace": {
        "calendar": [
            r"calendar\s+['\"]?([^'\"]+)['\"]?",
            r"['\"]?([^'\"]+)['\"]?\s+calendar",
        ],
        "folder": [
            r"folder\s+['\"]?([^'\"]+)['\"]?",
            r"in\s+['\"]?([^'\"]+)['\"]?\s+folder",
        ],
    },
    "shopify": {
        "order": [
            r"order[s]?\s+#?(\d+)",
            r"#(\d+)",
        ],
        "product": [
            r"product\s+['\"]?([^'\"]+)['\"]?",
        ],
    },
}


class ParameterInjectionService:
    """
    Automatically injects missing parameters into tool calls.

    When Claude calls a tool but forgets required parameters, this service
    attempts to extract them from the conversation history or configuration.

    Also maintains conversation context so follow-up questions work correctly.
    """

    # ==========================================================================
    # GENERIC CONTEXT EXTRACTION METHODS
    # ==========================================================================

    def extract_context_from_history(
        self,
        messages: List[Dict[str, Any]],
        datasource: str,
        context_type: str,
    ) -> Optional[str]:
        """
        Generic method to extract context from conversation history.

        Args:
            messages: Conversation history
            datasource: The active datasource (s3, jira, mysql, etc.)
            context_type: What to extract (bucket, project, table, etc.)

        Returns:
            Extracted context value or None
        """
        patterns = CONTEXT_PATTERNS.get(datasource, {}).get(context_type, [])
        if not patterns:
            return None

        # Search recent messages (most recent first)
        for msg in reversed(messages[-10:]):
            content = msg.get("content", "")
            if isinstance(content, str):
                content_lower = content.lower()
                for pattern in patterns:
                    match = re.search(pattern, content_lower, re.IGNORECASE)
                    if match:
                        # Get the captured group or full match
                        result = match.group(1) if match.lastindex else match.group(0)
                        logger.info(f"🔍 Found {context_type} context in history: {result}")
                        return result
        return None

    def has_context_in_query(
        self,
        query: str,
        datasource: str,
        context_type: str,
    ) -> bool:
        """
        Check if the query already contains the specified context.

        Args:
            query: The user's query
            datasource: The active datasource
            context_type: What to check for (bucket, project, table, etc.)

        Returns:
            True if context is present in query
        """
        patterns = CONTEXT_PATTERNS.get(datasource, {}).get(context_type, [])
        if not patterns:
            return False

        query_lower = query.lower()
        for pattern in patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def inject_parameters(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        datasource: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Inject missing parameters into a tool call.

        Args:
            tool_name: Name of the tool being called
            tool_input: Current tool input/arguments
            datasource: Active datasource
            messages: Conversation history for context extraction

        Returns:
            Updated tool_input with injected parameters
        """
        # Make a copy to avoid mutating the original
        updated_input = tool_input.copy()

        # Route to datasource-specific injection
        if datasource == "s3":
            updated_input = self._inject_s3_params(tool_name, updated_input, messages)
        elif datasource == "mysql":
            updated_input = self._inject_mysql_params(tool_name, updated_input, messages)
        elif datasource == "jira":
            updated_input = self._inject_jira_params(tool_name, updated_input, messages)
        elif datasource == "google_workspace":
            updated_input = self._inject_google_workspace_params(tool_name, updated_input, messages)
        elif datasource == "shopify":
            updated_input = self._inject_shopify_params(tool_name, updated_input, messages)

        return updated_input

    def _inject_s3_params(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Inject missing S3 parameters with conversation context support."""
        s3_tools_needing_bucket = ["list_objects", "read_object", "search_objects", "write_object"]

        if tool_name in s3_tools_needing_bucket:
            # Check if bucket is missing
            if "bucket" not in tool_input or not tool_input.get("bucket"):
                logger.info(f"Bucket parameter missing in {tool_name}, attempting auto-injection...")

                # First try the dedicated extractor
                bucket_name = parameter_extractor.extract_bucket_name(messages)

                # If not found, try generic context extraction from history
                if not bucket_name:
                    bucket_name = self.extract_context_from_history(messages, "s3", "bucket")

                if bucket_name:
                    tool_input["bucket"] = bucket_name
                    logger.info(f"✅ Auto-injected bucket parameter: {bucket_name}")
                else:
                    logger.warning(f"⚠️ Failed to extract bucket name from messages")
            else:
                logger.info(f"Bucket parameter already present: {tool_input.get('bucket')}")

        # Handle read_object key parameter
        if tool_name == "read_object":
            if "key" not in tool_input or not tool_input.get("key"):
                logger.info(f"Key parameter missing in read_object, attempting auto-extraction...")

                # First try the dedicated extractor
                key = parameter_extractor.extract_s3_key(messages)

                # If not found, try generic context extraction
                if not key:
                    key = self.extract_context_from_history(messages, "s3", "key")

                if key:
                    tool_input["key"] = key
                    logger.info(f"✅ Auto-injected key parameter: {key}")
                else:
                    logger.warning(f"⚠️ Failed to extract key from messages")
            else:
                logger.info(f"Key parameter already present: {tool_input.get('key')}")

            logger.info(f"🔍 READ_OBJECT CALL - bucket: {tool_input.get('bucket')}, key: {tool_input.get('key')}")

        return tool_input

    def _inject_mysql_params(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Inject missing MySQL parameters with conversation context support."""

        # describe_table needs table parameter
        if tool_name == "describe_table":
            if "table" not in tool_input or not tool_input.get("table"):
                logger.info(f"Table parameter missing in describe_table, attempting auto-injection...")
                table_name = parameter_extractor.extract_table_name(messages)

                # Try generic context extraction if not found
                if not table_name:
                    table_name = self.extract_context_from_history(messages, "mysql", "table")

                if table_name:
                    tool_input["table"] = table_name
                    logger.info(f"✅ Auto-injected table parameter: {table_name}")
                else:
                    logger.warning(f"⚠️ Failed to extract table name")

        # list_tables needs database parameter
        # NOTE: If no database is specified, we let the tool call fail and Claude
        # will then call list_databases to discover available databases.
        # We only inject if we find an explicit database name in the conversation.
        if tool_name == "list_tables":
            if "database" not in tool_input or not tool_input.get("database"):
                logger.info(f"Database parameter missing in list_tables, checking conversation context...")

                # Only try to extract from conversation if user mentioned a specific database
                db_name = parameter_extractor.extract_database_name(messages)

                # Also try generic context extraction from history
                if not db_name:
                    db_name = self.extract_context_from_history(messages, "mysql", "database")

                if db_name:
                    tool_input["database"] = db_name
                    logger.info(f"✅ Auto-injected database parameter: {db_name}")
                else:
                    # Don't inject anything - let Claude discover databases first
                    logger.info(f"⚠️ No database found in conversation - Claude should call list_databases first")

        # execute_query needs query parameter - add table context if missing
        if tool_name == "execute_query":
            if "query" not in tool_input or not tool_input.get("query"):
                logger.info(f"Query parameter missing in execute_query, attempting auto-construction...")
                query = parameter_extractor.construct_mysql_query(messages)
                if query:
                    tool_input["query"] = query
                    logger.info(f"✅ Auto-injected query parameter: {query}")
                else:
                    logger.warning(f"⚠️ Failed to construct query")
                    # Set a helpful error message so Claude knows what went wrong
                    tool_input["_error"] = "No SQL query provided. Please construct a SELECT statement."

            # Check if query references a table - if not, try to add context
            query = tool_input.get("query", "")
            if query and not self.has_context_in_query(query, "mysql", "table"):
                table_context = self.extract_context_from_history(messages, "mysql", "table")
                if table_context and "FROM" not in query.upper():
                    logger.info(f"✅ Found table context for query: {table_context}")

        # get_table_stats needs table parameter
        if tool_name == "get_table_stats":
            if "table" not in tool_input or not tool_input.get("table"):
                logger.info(f"Table parameter missing in get_table_stats, attempting auto-injection...")
                table_name = parameter_extractor.extract_table_name(messages)

                # Try generic context extraction if not found
                if not table_name:
                    table_name = self.extract_context_from_history(messages, "mysql", "table")

                if table_name:
                    tool_input["table"] = table_name
                    logger.info(f"✅ Auto-injected table parameter: {table_name}")
                else:
                    logger.warning(f"⚠️ Failed to extract table name")

        return tool_input

    def _inject_jira_params(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Inject missing JIRA parameters with conversation context support."""

        # query_jira needs query parameter
        if tool_name == "query_jira":
            if "query" not in tool_input or not tool_input.get("query"):
                logger.info(f"Query parameter missing in query_jira, attempting auto-injection...")

                # Get the most recent user message
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_query = msg.get("content")
                        if user_query and isinstance(user_query, str):
                            tool_input["query"] = user_query
                            logger.info(f"✅ Auto-injected query parameter from user message")
                            break

            # Check if query needs project context from conversation history
            query = tool_input.get("query", "")
            if query and not self.has_context_in_query(query, "jira", "project"):
                # Look for project context in conversation history using generic method
                project_context = self.extract_context_from_history(messages, "jira", "project")
                if project_context:
                    # Prepend project context to query
                    tool_input["query"] = f"{project_context}: {query}"
                    logger.info(f"✅ Added project context to query: {project_context}")

        return tool_input

    def _inject_google_workspace_params(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Inject missing Google Workspace parameters with conversation context support."""

        # Check if user_google_email needs injection
        current_email = tool_input.get("user_google_email", "")
        is_invalid = not current_email or "@" not in current_email or "placeholder" in current_email.lower()

        if is_invalid and settings.user_google_email:
            tool_input["user_google_email"] = settings.user_google_email
            logger.info(f"✅ Auto-injected user_google_email: {settings.user_google_email} (replaced: {current_email})")
        elif is_invalid:
            logger.warning(f"⚠️ USER_GOOGLE_EMAIL not configured in settings")

        # Add folder context for Drive operations
        if tool_name == "search_drive_files":
            query = tool_input.get("query", "")
            if query and not self.has_context_in_query(query, "google_workspace", "folder"):
                folder_context = self.extract_context_from_history(messages, "google_workspace", "folder")
                if folder_context:
                    tool_input["query"] = f"in folder '{folder_context}': {query}"
                    logger.info(f"✅ Added folder context to query: {folder_context}")

        # Add calendar context for calendar operations
        if tool_name == "get_events":
            if "calendar_id" not in tool_input or not tool_input.get("calendar_id"):
                calendar_context = self.extract_context_from_history(messages, "google_workspace", "calendar")
                if calendar_context:
                    tool_input["calendar_id"] = calendar_context
                    logger.info(f"✅ Auto-injected calendar_id: {calendar_context}")

        return tool_input

    def _inject_shopify_params(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Inject missing Shopify parameters with conversation context support."""

        # Add order context for order-related operations
        if tool_name in ["get_order", "update_order"]:
            if "order_id" not in tool_input or not tool_input.get("order_id"):
                order_context = self.extract_context_from_history(messages, "shopify", "order")
                if order_context:
                    tool_input["order_id"] = order_context
                    logger.info(f"✅ Auto-injected order_id: {order_context}")

        # Add product context for product-related operations
        if tool_name in ["get_product", "update_product"]:
            if "product_id" not in tool_input or not tool_input.get("product_id"):
                product_context = self.extract_context_from_history(messages, "shopify", "product")
                if product_context:
                    tool_input["product_id"] = product_context
                    logger.info(f"✅ Auto-injected product_id: {product_context}")

        return tool_input

    def needs_parameter_injection(self, tool_name: str, datasource: str) -> bool:
        """
        Check if a tool might need parameter injection.

        Useful for deciding whether to log/trace parameter injection.

        Args:
            tool_name: Name of the tool
            datasource: Active datasource

        Returns:
            True if the tool might need parameter injection
        """
        injection_candidates = {
            "s3": ["list_objects", "read_object", "search_objects", "write_object"],
            "mysql": ["describe_table", "list_tables", "execute_query", "get_table_stats"],
            "jira": ["query_jira", "get_issue", "search_issues"],
            "google_workspace": ["get_events", "list_messages", "search_drive_files"],
            "shopify": ["get_order", "update_order", "get_product", "update_product", "list_orders"],
        }

        return tool_name in injection_candidates.get(datasource, [])


# Global instance for import
parameter_injection_service = ParameterInjectionService()

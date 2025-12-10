"""Parameter extraction for S3, MySQL, and JIRA queries."""

import re
import json
import logging
from typing import List, Optional
from urllib.parse import unquote_plus

from app.core.config import settings

logger = logging.getLogger(__name__)


class ParameterExtractor:
    """Extracts parameters from user messages for various datasources."""

    # Common words to exclude from table/database name extraction
    EXCLUDE_WORDS = {
        'the', 'a', 'an', 'all', 'any', 'some', 'what', 'which', 'where',
        'when', 'how', 'about', 'that', 'this', 'these', 'those', 'common',
        'exist', 'structure', 'schema', 'database', 'table', 'column', 'row',
        'data', 'information', 'content', 'kind', 'type', 'direct', 'directly',
        'show', 'get', 'latest', 'first', 'last', 'recent', 'me', 'my'
    }

    # S3 Methods
    def extract_bucket_name(self, messages: List[dict]) -> Optional[str]:
        """Extract S3 bucket name from user messages."""
        # Look through user messages for bucket names
        for message in reversed(messages):  # Start from most recent
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    # Generic patterns for bucket names (S3 naming rules: 3-63 chars, lowercase, numbers, hyphens)
                    patterns = [
                        r'bucket[:\s]+([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
                        r'contents?\s+of\s+([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])',
                        r'(?:in|from)\s+(?:the\s+)?([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])\s+bucket',
                        r'([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])\s+bucket',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            bucket_name = match.group(1).lower()
                            # Validate basic S3 bucket naming rules
                            if 3 <= len(bucket_name) <= 63 and not bucket_name.startswith('-') and not bucket_name.endswith('-'):
                                return bucket_name

        return None

    def extract_s3_key(self, messages: List[dict]) -> Optional[str]:
        """Extract S3 object key by finding it in previous list_objects results."""
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
                            except (json.JSONDecodeError, KeyError, TypeError):
                                pass

        logger.info(f"Available S3 keys from conversation (raw): {available_keys[:3]}...")

        # URL-decode the keys for better matching
        decoded_keys = [(key, unquote_plus(key)) for key in available_keys]
        logger.info(f"Decoded keys (first 3): {[(k, d) for k, d in decoded_keys[:3]]}")

        # Now find the most recent user request mentioning a file
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    logger.info(f"Checking user message for file reference: {content[:200]}")
                    content_lower = content.lower()

                    # For each available key, see if it's mentioned in the user message
                    best_match = None
                    best_match_score = 0

                    for raw_key, decoded_key in decoded_keys:
                        # Work with the decoded version for matching
                        decoded_base = decoded_key
                        for ext in ['.md', '.txt', '.pdf', '.docx', '.doc']:
                            decoded_base = decoded_base.replace(ext, '').replace(ext.upper(), '')

                        decoded_base_lower = decoded_base.lower()

                        # Normalize the key: remove spaces, special chars
                        key_normalized = re.sub(r'[^a-z0-9]', '', decoded_base_lower)

                        # Strategy 1: Direct substring match in original text
                        if decoded_base_lower in content_lower:
                            logger.info(f"EXACT match! '{decoded_key}'")
                            return raw_key

                        # Strategy 2: Check if normalized key appears as substring in user message
                        content_normalized = re.sub(r'[^a-z0-9]', '', content_lower)
                        if key_normalized in content_normalized or content_normalized in key_normalized:
                            logger.info(f"Normalized match! '{decoded_key}'")
                            return raw_key

                        # Strategy 3: Check for combined words (e.g., "nicecx" should match "nice cx")
                        key_no_spaces = decoded_base_lower.replace(' ', '').replace('-', '')
                        if key_no_spaces in content_normalized:
                            logger.info(f"Combined word match! '{decoded_key}' (as '{key_no_spaces}')")
                            return raw_key

                        # Also check if content (without spaces) appears in key
                        for content_word in re.findall(r'\w+', content_lower):
                            if len(content_word) > 4:  # Only check substantial words
                                if content_word in key_no_spaces:
                                    logger.info(f"Partial combined match! Found '{content_word}' in '{decoded_key}'")
                                    return raw_key

                        # Strategy 4: Word-based fuzzy matching with scoring
                        key_words = set(re.findall(r'\w+', decoded_base_lower))
                        key_words = {w for w in key_words if len(w) > 2}
                        content_words = set(re.findall(r'\w+', content_lower))
                        content_words = {w for w in content_words if len(w) > 2}
                        common_words = key_words & content_words

                        # Calculate match score based on common words
                        match_score = len(common_words)

                        # Boost score for longer/more distinctive words
                        for word in common_words:
                            if len(word) > 5:
                                match_score += 1
                            if len(word) > 8:
                                match_score += 1

                        if match_score > best_match_score:
                            best_match = raw_key
                            best_match_score = match_score
                            logger.info(f"Candidate: '{decoded_key}' with score {match_score} (common words: {common_words})")

                    # If we found a fuzzy match, return it
                    if best_match and best_match_score >= 2:
                        logger.info(f"Best match with score {best_match_score}: {best_match}")
                        return best_match

        # If only one key is available, use it
        if len(available_keys) == 1:
            logger.info(f"Only one key available, using it: {available_keys[0]}")
            return available_keys[0]

        logger.warning(f"Could not extract S3 key from messages. Had {len(available_keys)} keys available.")
        return None

    # MySQL Methods
    def extract_table_name(self, messages: List[dict]) -> Optional[str]:
        """Extract MySQL table name from user messages."""
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
                        r'(?:latest|recent|first|last)\s+(?:\d+\s+)?([a-z_][a-z0-9_]*)',
                        r'(?:show|get|list|display)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?([a-z_][a-z0-9_]*)',
                        r'how\s+many\s+([a-z_][a-z0-9_]*)',
                        r'count\s+(?:of\s+)?([a-z_][a-z0-9_]*)',
                        r'(?:select|query)\s+(?:from\s+)?([a-z_][a-z0-9_]*)',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            table_name = match.group(1).lower()
                            # Filter out common words
                            if table_name not in self.EXCLUDE_WORDS and len(table_name) > 2:
                                logger.info(f"Extracted table name: {table_name}")
                                return table_name

        return None

    def extract_database_name(self, messages: List[dict]) -> Optional[str]:
        """Extract MySQL database name from user messages.

        Returns None if no database name found - let Claude handle it or
        use the database from user's credentials.
        """
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
                            if db_name not in self.EXCLUDE_WORDS and len(db_name) > 2:
                                logger.info(f"Extracted database name: {db_name}")
                                return db_name

        # Don't use a default - let Claude handle it or use user's configured database
        logger.info(f"No database name found in messages")
        return None

    def construct_mysql_query(self, messages: List[dict]) -> Optional[str]:
        """Construct a SELECT query from natural language in user messages."""
        # Look through user messages for query intentions
        for message in reversed(messages):  # Start from most recent
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    content_lower = content.lower()

                    # Extract table name
                    table_name = self.extract_table_name(messages)
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
                        num_match = re.search(r'(?:latest|recent)\s+(\d+)', content_lower)
                        if num_match:
                            limit = int(num_match.group(1))
                        else:
                            limit = 10  # Default for "latest" queries

                    # Check if we need ORDER BY DESC for "latest" or "recent"
                    order_by = ""
                    if 'latest' in content_lower or 'recent' in content_lower or 'last' in content_lower:
                        possible_columns = [
                            f"{table_name.rstrip('s')}_id",
                            "id",
                            "created_at",
                            "updated_at"
                        ]
                        order_column = possible_columns[0]
                        order_by = f" ORDER BY {order_column} DESC"

                    # Construct query
                    query = f"SELECT * FROM {table_name}{order_by} LIMIT {limit}"
                    logger.info(f"Constructed query: {query}")
                    return query

        return None

    # JIRA Methods
    def extract_jira_project_key(self, messages: List[dict], available_projects: List[str] = None) -> Optional[str]:
        """Extract JIRA project key from user messages."""
        if not available_projects:
            return None

        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    content_lower = content.lower()

                    # Check for exact project key matches
                    for project in available_projects:
                        if project.lower() in content_lower:
                            logger.info(f"Found JIRA project key: {project}")
                            return project

        return None

    def extract_jira_assignee(self, messages: List[dict]) -> Optional[str]:
        """Extract assignee name from user messages for JIRA queries."""
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    # Common patterns for assignee
                    patterns = [
                        r'assigned\s+to\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
                        r'(?:what|which|show)\s+(?:has|did)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(?:done|worked|completed)',
                        r"([A-Za-z]+(?:\s+[A-Za-z]+)?)'s\s+(?:tasks?|issues?|tickets?|work)",
                        r'by\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            assignee = match.group(1).strip()
                            # Filter out common words
                            if assignee.lower() not in self.EXCLUDE_WORDS:
                                logger.info(f"Extracted JIRA assignee: {assignee}")
                                return assignee

        return None

    def extract_jira_status(self, messages: List[dict]) -> Optional[str]:
        """Extract status from user messages for JIRA queries."""
        status_keywords = {
            'done': 'Done',
            'completed': 'Done',
            'finished': 'Done',
            'in progress': 'In Progress',
            'in-progress': 'In Progress',
            'working on': 'In Progress',
            'todo': 'To Do',
            'to do': 'To Do',
            'open': 'Open',
            'closed': 'Closed',
            'resolved': 'Resolved',
        }

        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    content_lower = content.lower()
                    for keyword, status in status_keywords.items():
                        if keyword in content_lower:
                            logger.info(f"Extracted JIRA status: {status}")
                            return status

        return None


# Global parameter extractor instance
parameter_extractor = ParameterExtractor()

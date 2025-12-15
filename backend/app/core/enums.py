"""
Enums and constants for ConnectorMCP.

Replaces magic strings with type-safe enums throughout the codebase.
"""

from enum import Enum
from typing import Set


class DataSourceType(str, Enum):
    """Supported data source types."""

    S3 = "s3"
    JIRA = "jira"
    MYSQL = "mysql"
    SLACK = "slack"
    GOOGLE_WORKSPACE = "google_workspace"
    SHOPIFY = "shopify"
    GITHUB = "github"

    @classmethod
    def values(cls) -> Set[str]:
        """Get all valid datasource values."""
        return {member.value for member in cls}

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid datasource."""
        return value in cls.values()


class MessageRole(str, Enum):
    """Chat message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgentStepType(str, Enum):
    """Types of agent activity steps."""

    THINKING = "thinking"
    PLANNING = "planning"
    TOOL_CALL = "tool_call"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    ERROR = "error"


class AgentStepStatus(str, Enum):
    """Status of agent activity steps."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"
    ERROR = "error"


class RoutingPath(str, Enum):
    """Routing paths for the three-tier system."""

    DIRECT = "direct"  # Instant routing, no LLM
    HAIKU = "haiku"  # Fast LLM for tool selection
    SONNET = "sonnet"  # Full LLM for complex queries


class CacheType(str, Enum):
    """Types of caches in the system."""

    TOOLS = "tools"  # Tool definitions cache
    RESULTS = "results"  # Tool result cache
    SCHEMA = "schema"  # Database schema cache
    SESSION = "session"  # Chat session cache


# ============ Tool Names by Datasource ============


class S3Tools(str, Enum):
    """S3 MCP tool names."""

    LIST_BUCKETS = "list_buckets"
    LIST_OBJECTS = "list_objects"
    READ_OBJECT = "read_object"
    SEARCH_OBJECTS = "search_objects"
    GET_OBJECT_METADATA = "get_object_metadata"


class SlackTools(str, Enum):
    """Slack MCP tool names."""

    LIST_CHANNELS = "list_channels"
    GET_CHANNEL_INFO = "get_channel_info"
    READ_MESSAGES = "read_messages"
    SEARCH_MESSAGES = "search_messages"
    LIST_USERS = "list_users"
    GET_USER_INFO = "get_user_info"
    GET_USER_PRESENCE = "get_user_presence"
    GET_THREAD_REPLIES = "get_thread_replies"
    LIST_FILES = "list_files"
    READ_DM_WITH_USER = "read_dm_with_user"
    GET_USER_MESSAGES_IN_CHANNEL = "get_user_messages_in_channel"
    LIST_DMS = "list_dms"
    SEARCH_IN_DMS = "search_in_dms"
    GET_CHANNEL_ACTIVITY = "get_channel_activity"
    SEND_MESSAGE = "send_message"
    SEND_DM = "send_dm"


class JiraTools(str, Enum):
    """JIRA MCP tool names."""

    LIST_PROJECTS = "list_projects"
    QUERY_JIRA = "query_jira"
    GET_ISSUE = "get_issue"
    CREATE_ISSUE = "create_issue"
    UPDATE_ISSUE = "update_issue"


class MySQLTools(str, Enum):
    """MySQL MCP tool names."""

    LIST_TABLES = "list_tables"
    DESCRIBE_TABLE = "describe_table"
    EXECUTE_QUERY = "execute_query"
    GET_TABLE_STATS = "get_table_stats"


class GoogleWorkspaceTools(str, Enum):
    """Google Workspace MCP tool names."""

    LIST_DOCS = "list_docs"
    LIST_SHEETS = "list_sheets"
    LIST_CALENDAR_EVENTS = "list_calendar_events"
    GET_DOC_CONTENT = "get_doc_content"
    GET_SHEET_DATA = "get_sheet_data"


class GitHubTools(str, Enum):
    """GitHub MCP tool names."""

    LIST_REPOS = "list_repos"
    LIST_PULL_REQUESTS = "list_pull_requests"
    LIST_ISSUES = "list_issues"
    GET_REPO_INFO = "get_repo_info"


# ============ Model Names ============


class ClaudeModel(str, Enum):
    """Claude model identifiers."""

    HAIKU = "claude-3-5-haiku-20241022"
    SONNET = "claude-sonnet-4-5-20250929"
    OPUS = "claude-opus-4-5-20251101"


# ============ Environment ============


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

    @classmethod
    def is_production(cls, env: str) -> bool:
        """Check if environment is production."""
        return env.lower() == cls.PRODUCTION.value


# ============ Event Types ============


class SSEEventType(str, Enum):
    """Server-Sent Event types for streaming."""

    SESSION = "session"
    CONTENT = "content"
    THINKING_START = "thinking_start"
    THINKING = "thinking"
    THINKING_END = "thinking_end"
    AGENT_STEP = "agent_step"
    SOURCE = "source"
    DONE = "done"
    ERROR = "error"


# ============ Cache TTLs (in seconds) ============


class CacheTTL:
    """Cache time-to-live values in seconds."""

    TOOLS = 300  # 5 minutes for tool definitions
    RESULTS = 30  # 30 seconds for query results
    SCHEMA = 600  # 10 minutes for database schemas
    SESSION = 86400  # 24 hours for chat sessions
    CREDENTIALS = 3600  # 1 hour for credential cache


# ============ Limits ============


class Limits:
    """System limits and constraints."""

    MAX_MESSAGE_LENGTH = 100000  # Max characters in a message
    MAX_TOOL_ITERATIONS = 25  # Max tool call iterations per request
    MAX_RESULT_CACHE_SIZE = 100  # Max cached results
    MAX_STREAMING_TIMEOUT = 120  # Seconds
    MAX_TOOL_TIMEOUT = 60  # Seconds for tool execution
    MAX_SESSION_MESSAGES = 1000  # Max messages per session

    # Rate limits
    REQUESTS_PER_MINUTE = 60
    REQUESTS_PER_HOUR = 1000

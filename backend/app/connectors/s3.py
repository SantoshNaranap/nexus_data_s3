"""
Amazon S3 connector configuration.

Provides MCP tools for interacting with S3 buckets:
- Listing buckets and objects
- Reading and writing objects
- Searching objects
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class S3Connector(BaseConnector):
    """Amazon S3 connector configuration."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="s3",
            name="Amazon S3",
            description="Query and manage S3 buckets and objects",
            icon="s3",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        return [
            CredentialField(
                name="aws_access_key_id",
                env_var="AWS_ACCESS_KEY_ID",
                display_name="Access Key ID",
                description="AWS Access Key ID",
                required=True,
            ),
            CredentialField(
                name="aws_secret_access_key",
                env_var="AWS_SECRET_ACCESS_KEY",
                display_name="Secret Access Key",
                description="AWS Secret Access Key",
                required=True,
            ),
            CredentialField(
                name="aws_default_region",
                env_var="AWS_DEFAULT_REGION",
                display_name="Region",
                description="AWS Region (e.g., us-east-1)",
                required=False,
                sensitive=False,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/s3/src/s3_server.py"

    @property
    def prewarm_on_startup(self) -> bool:
        return True

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "list_buckets",
            "list_objects",
            "search_objects",
        ]

    @property
    def system_prompt_addition(self) -> str:
        return """
S3 TOOLS - COMPREHENSIVE GUIDE:

**PRIMARY TOOLS:**
- `list_buckets()` - List ALL buckets in the AWS account. ALWAYS start here.
- `list_objects(bucket, prefix)` - List files in a bucket. Use prefix for folders.
- `read_object(bucket, key)` - Read file contents. Key must be EXACT from list_objects.
- `search_objects(bucket, query)` - Search for files by name pattern.

**CRITICAL RULES - NEVER VIOLATE:**
1. ALWAYS call `list_buckets()` first if you don't know the bucket names
2. ALWAYS call `list_objects()` before `read_object()` to get exact keys
3. NEVER say "I don't have access" without calling a tool first
4. NEVER say "file not found" without searching first
5. ALWAYS show the actual file contents when reading

**WORKFLOW EXAMPLES:**

"What's in my S3?" or "Show my buckets":
→ Call list_buckets() and display ALL results

"Show files in [bucket]" or "Contents of [bucket]":
→ Call list_objects(bucket="bucket-name") and display ALL files

"Read [filename]" or "Show me [document]":
→ Step 1: list_objects() to find exact key
→ Step 2: read_object(bucket, key) with EXACT key from step 1
→ Step 3: Display the FULL contents

"Find files about [topic]":
→ Call search_objects(bucket, query)
→ Then read_object() for each relevant match

**KEY RULES:**
- The "key" parameter must be EXACTLY as returned by list_objects
- Do NOT modify keys (no URL encoding changes)
- If user asks about a file, FIND it and READ it - don't give up
- Show ALL data - never truncate or summarize unless asked
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common S3 queries."""
        import re
        message_lower = message.lower().strip()

        # Check if asking about contents of a SPECIFIC bucket
        # Patterns like "what is in [bucket]", "contents of [bucket]", "files in [bucket]"
        content_patterns = [
            r"what(?:'s| is) in (?:the )?(\S+)(?: bucket)?",
            r"(?:show|list|get) (?:me )?(?:the )?(?:contents?|files?|objects?) (?:of |in |from )?(?:the )?(\S+)(?: bucket)?",
            r"contents? of (?:the )?(\S+)(?: bucket)?",
            r"files? in (?:the )?(\S+)(?: bucket)?",
            r"(\S+) bucket(?:'s)? (?:contents?|files?|objects?)",
        ]

        for pattern in content_patterns:
            match = re.search(pattern, message_lower)
            if match:
                bucket_name = match.group(1).strip("'\"")
                # Skip if the matched word is a generic term, not a bucket name
                if bucket_name not in ["my", "the", "a", "all", "s3", "bucket", "buckets"]:
                    return [{"tool": "list_objects", "args": {"bucket": bucket_name}}]

        # List all buckets - only when asking generically
        list_bucket_patterns = [
            "list buckets",
            "list my buckets",
            "show buckets",
            "show my buckets",
            "what buckets",
            "which buckets",
            "my s3 buckets",
            "all buckets",
        ]
        if any(pattern in message_lower for pattern in list_bucket_patterns):
            return [{"tool": "list_buckets", "args": {}}]

        return None


# Export singleton instance
s3_connector = S3Connector()

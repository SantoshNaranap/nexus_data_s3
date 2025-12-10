"""Claude API client wrapper for chat interactions."""

import logging
import random
from typing import List, Dict, Any, Optional, AsyncGenerator
from anthropic import Anthropic
from anthropic.types import ToolUseBlock, TextBlock

from app.core.config import settings

logger = logging.getLogger(__name__)

# Default model
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 4096
MAX_ITERATIONS = 10  # Reduced from 25 to prevent endless retry loops


def get_quirky_thinking_message(tool_name: str) -> str:
    """Generate clean, professional status messages based on tool name."""
    status_messages = {
        "list": [
            "Retrieving list...",
            "Fetching items...",
            "Loading data...",
        ],
        "read": [
            "Reading content...",
            "Loading file...",
            "Fetching data...",
        ],
        "search": [
            "Searching...",
            "Looking up results...",
            "Finding matches...",
        ],
        "get": [
            "Fetching data...",
            "Retrieving information...",
            "Loading...",
        ],
        "create": [
            "Creating...",
            "Building...",
            "Setting up...",
        ],
        "update": [
            "Updating...",
            "Applying changes...",
            "Modifying...",
        ],
        "delete": [
            "Removing...",
            "Deleting...",
            "Cleaning up...",
        ],
        "query": [
            "Querying...",
            "Running query...",
            "Fetching results...",
        ],
    }

    tool_lower = tool_name.lower()
    for pattern, messages in status_messages.items():
        if pattern in tool_lower:
            return random.choice(messages)

    default_messages = [
        "Processing...",
        "Working...",
        "Loading...",
    ]
    return random.choice(default_messages)


class ClaudeClient:
    """Wrapper for Anthropic Claude API interactions."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Claude client."""
        self.api_key = api_key or settings.anthropic_api_key
        self.client = Anthropic(api_key=self.api_key)
        self.model = DEFAULT_MODEL

    def create_message(
        self,
        messages: List[dict],
        system_prompt: str,
        tools: Optional[List[dict]] = None,
        max_tokens: int = MAX_TOKENS,
    ):
        """Create a non-streaming message."""
        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools if tools else None,
        )

    def stream_message(
        self,
        messages: List[dict],
        system_prompt: str,
        tools: Optional[List[dict]] = None,
        max_tokens: int = MAX_TOKENS,
    ):
        """Create a streaming message."""
        return self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools if tools else None,
        )

    @staticmethod
    def extract_tool_use_blocks(response) -> List[ToolUseBlock]:
        """Extract tool use blocks from a response."""
        return [
            block for block in response.content
            if isinstance(block, ToolUseBlock)
        ]

    @staticmethod
    def extract_text_blocks(response) -> str:
        """Extract text content from a response."""
        text_blocks = [
            block for block in response.content
            if isinstance(block, TextBlock)
        ]
        return "\n".join(block.text for block in text_blocks)

    @staticmethod
    def format_tool_result(tool_use_id: str, content: str, is_error: bool = False) -> dict:
        """Format a tool result for inclusion in messages."""
        result = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }
        if is_error:
            result["is_error"] = True
        return result


# Global Claude client instance
claude_client = ClaudeClient()

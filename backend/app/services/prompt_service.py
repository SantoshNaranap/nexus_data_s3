"""
Prompt Service - Thin wrapper around centralized prompts.

NOTE: All prompts are now defined in app/core/prompts.py
This service is kept for backwards compatibility with existing imports.

For new code, prefer importing directly from app.core.prompts:
    from app.core.prompts import Prompts
"""

import logging
from typing import Optional

from app.core.prompts import Prompts

logger = logging.getLogger(__name__)


class PromptService:
    """
    Generates system prompts for Claude based on the active data source.

    This is now a thin wrapper around the centralized Prompts class.
    All prompt definitions are in app/core/prompts.py for easier management.
    """

    def get_system_prompt(self, datasource: str, connector_name: Optional[str] = None) -> str:
        """
        Generate the complete system prompt for a datasource.

        Args:
            datasource: The datasource ID (e.g., 'jira', 's3', 'mysql')
            connector_name: Optional display name for the connector

        Returns:
            Complete system prompt string
        """
        return Prompts.get_system_prompt(datasource, connector_name)

    def get_datasource_specific_prompt(self, datasource: str) -> str:
        """Get datasource-specific prompt additions."""
        return Prompts.datasources.get(datasource)


# Backwards compatibility function
def get_system_prompt_addition(datasource: str) -> str:
    """
    Get datasource-specific system prompt additions.

    DEPRECATED: Use Prompts.datasources.get(datasource) directly.
    """
    return Prompts.datasources.get(datasource)


# Global instance for import
prompt_service = PromptService()

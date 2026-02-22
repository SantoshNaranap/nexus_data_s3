"""
Connector Registry

This module provides a centralized registry for all connector configurations.
To add a new connector:
1. Create a new file in app/connectors/ (e.g., myconnector.py)
2. Create a class that inherits from BaseConnector
3. Import and register it in the CONNECTORS dict below

Example:
    from .myconnector import myconnector
    CONNECTORS = {
        ...
        "myconnector": myconnector,
    }
"""

import logging
from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField

# Import all connector instances
from .s3 import s3_connector
from .jira import jira_connector
from .mysql import mysql_connector
from .slack import slack_connector
from .google_workspace import google_workspace_connector
from .shopify import shopify_connector
from .github import github_connector

logger = logging.getLogger(__name__)

# Registry of all available connectors
# Key: connector ID (used in URLs, database, etc.)
# Value: connector instance
CONNECTORS: Dict[str, BaseConnector] = {
    "s3": s3_connector,
    "jira": jira_connector,
    "mysql": mysql_connector,
    "slack": slack_connector,
    "google_workspace": google_workspace_connector,
    "shopify": shopify_connector,
    "github": github_connector,
}


def get_connector(connector_id: str) -> Optional[BaseConnector]:
    """
    Get a connector by ID.

    Args:
        connector_id: The connector identifier (e.g., "slack", "jira")

    Returns:
        The connector instance, or None if not found
    """
    return CONNECTORS.get(connector_id)


def get_all_connectors() -> Dict[str, BaseConnector]:
    """Get all registered connectors."""
    return CONNECTORS.copy()


def get_connector_ids() -> List[str]:
    """Get list of all connector IDs."""
    return list(CONNECTORS.keys())


def get_available_datasources() -> List[Dict[str, Any]]:
    """
    Get list of available data sources for API responses.

    Returns:
        List of connector metadata dicts for UI display
    """
    return [connector.to_dict() for connector in CONNECTORS.values()]


def get_system_prompt_addition(connector_id: str) -> str:
    """
    Get the system prompt addition for a connector.

    Args:
        connector_id: The connector identifier

    Returns:
        System prompt string, or empty string if connector not found
    """
    connector = get_connector(connector_id)
    if connector:
        return connector.system_prompt_addition
    return ""


def get_direct_routing(connector_id: str, message: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get direct tool routing for a message.

    Args:
        connector_id: The connector identifier
        message: The user's message

    Returns:
        List of tool calls, or None if no direct routing applies
    """
    connector = get_connector(connector_id)
    if connector:
        return connector.get_direct_routing(message)
    return None


def get_cacheable_tools(connector_id: str) -> List[str]:
    """
    Get list of cacheable tools for a connector.

    Args:
        connector_id: The connector identifier

    Returns:
        List of tool names that can be cached
    """
    connector = get_connector(connector_id)
    if connector:
        return connector.cacheable_tools
    return []


def get_connectors_to_prewarm() -> List[str]:
    """
    Get list of connector IDs that should be pre-warmed on startup.

    Returns:
        List of connector IDs
    """
    return [
        connector_id
        for connector_id, connector in CONNECTORS.items()
        if connector.prewarm_on_startup
    ]


def get_credential_env_mapping(connector_id: str) -> Dict[str, str]:
    """
    Get the credential field to environment variable mapping.

    Args:
        connector_id: The connector identifier

    Returns:
        Dict mapping field names to env var names
    """
    connector = get_connector(connector_id)
    if connector:
        return {field.name: field.env_var for field in connector.credential_fields}
    return {}


def get_connector_env(
    connector_id: str,
    credentials: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Get the full environment variables dict for running a connector.

    Args:
        connector_id: The connector identifier
        credentials: Optional user credentials to merge

    Returns:
        Dict of environment variables
    """
    connector = get_connector(connector_id)
    if not connector:
        return {}

    # Start with additional env vars
    env = connector.additional_env.copy()

    # Merge user credentials if provided
    if credentials:
        env.update(connector.get_env_from_credentials(credentials))

    return env


def get_server_config(connector_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the server configuration for running a connector's MCP server.

    Args:
        connector_id: The connector identifier

    Returns:
        Dict with 'command', 'args', and 'env' keys
    """
    connector = get_connector(connector_id)
    if not connector:
        return None

    command, args = connector.get_server_command()
    return {
        "command": command,
        "args": args,
        "env": connector.additional_env,
    }


# Re-export for convenience
__all__ = [
    "BaseConnector",
    "ConnectorMetadata",
    "CredentialField",
    "CONNECTORS",
    "get_connector",
    "get_all_connectors",
    "get_connector_ids",
    "get_available_datasources",
    "get_system_prompt_addition",
    "get_direct_routing",
    "get_cacheable_tools",
    "get_connectors_to_prewarm",
    "get_credential_env_mapping",
    "get_connector_env",
    "get_server_config",
]

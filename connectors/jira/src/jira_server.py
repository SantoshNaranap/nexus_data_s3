#!/usr/bin/env python3
"""
JIRA MCP Server

Provides MCP tools for interacting with JIRA issues and projects.
Supports both Basic Auth (API token) and OAuth (Bearer token) authentication.

PRODUCTION-READY: Uses lazy initialization to handle expired OAuth tokens gracefully.
"""

import json
import logging
import os
from typing import Any, Optional

from jira import JIRA
from jira.exceptions import JIRAError
from mcp.server import Server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jira-mcp-server")

# Get JIRA credentials from environment
jira_url = os.getenv("JIRA_URL", "")
jira_email = os.getenv("JIRA_EMAIL", "")
jira_api_token = os.getenv("JIRA_API_TOKEN", "")
jira_cloud_id = os.getenv("JIRA_CLOUD_ID", "")

# Global client - lazily initialized
_jira_client: Optional[JIRA] = None
_initialization_error: Optional[str] = None


def get_jira_client() -> JIRA:
    """
    Lazily initialize and return the JIRA client.

    This allows the MCP server to start even if credentials are expired,
    and returns a clear error message when authentication fails.
    """
    global _jira_client, _initialization_error

    # Return cached client if available
    if _jira_client is not None:
        return _jira_client

    # If we already tried and failed, raise the cached error
    if _initialization_error is not None:
        raise JIRAError(_initialization_error)

    try:
        if jira_cloud_id:
            # OAuth mode - use Atlassian Cloud API with Bearer token
            oauth_base_url = f"https://api.atlassian.com/ex/jira/{jira_cloud_id}"
            logger.info(f"Initializing OAuth mode with Cloud ID: {jira_cloud_id[:8]}...")

            _jira_client = JIRA(
                server=oauth_base_url,
                options={"headers": {"Authorization": f"Bearer {jira_api_token}"}},
            )
        else:
            # Basic Auth mode - use instance URL with email + API token
            url = jira_url
            if url and not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            logger.info(f"Initializing Basic Auth mode with JIRA URL: {url}")
            _jira_client = JIRA(
                server=url,
                basic_auth=(jira_email, jira_api_token),
            )

        logger.info("JIRA client initialized successfully")
        return _jira_client

    except JIRAError as e:
        error_msg = str(e)
        # Check for authentication errors
        if "401" in error_msg or "Unauthorized" in error_msg or "FAILURE_CLIENT_AUTH" in error_msg:
            _initialization_error = "AUTH_ERROR_401: Your Jira OAuth token has expired. Please reconnect your Jira account in Settings."
            logger.error(f"Jira authentication failed (token likely expired): {error_msg[:200]}")
        else:
            _initialization_error = f"JIRA_ERROR: {error_msg}"
            logger.error(f"Jira initialization failed: {error_msg[:200]}")
        raise JIRAError(_initialization_error)
    except Exception as e:
        _initialization_error = f"JIRA_ERROR: Failed to connect to Jira - {str(e)}"
        logger.error(f"Unexpected error initializing Jira: {e}")
        raise JIRAError(_initialization_error)


def handle_jira_error(e: Exception, operation: str) -> list[TextContent]:
    """
    Handle JIRA errors with user-friendly messages.
    Returns structured error that the backend can detect for token refresh.
    """
    error_str = str(e)

    # Check for authentication errors
    if any(pattern in error_str for pattern in ['401', 'Unauthorized', 'AUTH_ERROR_401', 'FAILURE_CLIENT_AUTH']):
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": True,
                "error_code": "AUTH_ERROR_401",
                "message": "Your Jira OAuth token has expired. Please reconnect your Jira account in Settings.",
                "requires_reauth": True,
            })
        )]

    # Other JIRA errors
    logger.error(f"JIRA error in {operation}: {error_str}")
    return [TextContent(
        type="text",
        text=json.dumps({
            "error": True,
            "error_code": "JIRA_ERROR",
            "message": f"Jira error: {error_str[:500]}",
        })
    )]


# Create MCP server
app = Server("jira-connector")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available JIRA tools."""
    return [
        Tool(
            name="search_issues",
            description="""Search for JIRA issues using JQL (JIRA Query Language).

IMPORTANT: Always call list_projects FIRST to get the correct project key!

Common JQL examples:
- All issues in a project: 'project = SH' (use exact project key from list_projects)
- Open issues: 'project = SH AND status != Closed'
- By status: 'project = SH AND status = "In Progress"'
- By assignee: 'project = SH AND assignee = "John Doe"'
- Multiple conditions: 'project = SH AND status = "In Progress" AND assignee = currentUser()'
- Recent updates: 'project = SH AND updated >= -7d'
- By priority: 'project = SH AND priority = High'
- Unassigned: 'project = SH AND assignee is EMPTY'

ALWAYS include 'project = PROJECTKEY' to filter to the correct project!""",
            inputSchema={
                "type": "object",
                "properties": {
                    "jql": {
                        "type": "string",
                        "description": "JQL query string. REQUIRED. Cannot be empty. Example: 'status = Open' to get all open issues",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of issues to return (default: 50)",
                        "default": 50,
                    },
                    "fields": {
                        "type": "string",
                        "description": "Comma-separated fields to return (default: key,summary,status,assignee)",
                    },
                },
                "required": ["jql"],
            },
        ),
        Tool(
            name="get_issue",
            description="Get detailed information about a specific JIRA issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "The issue key (e.g., 'PROJ-123')",
                    },
                },
                "required": ["issue_key"],
            },
        ),
        Tool(
            name="create_issue",
            description="Create a new JIRA issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project key",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Issue summary/title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Issue description",
                    },
                    "issue_type": {
                        "type": "string",
                        "description": "Issue type (e.g., 'Bug', 'Task', 'Story')",
                        "default": "Task",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority (e.g., 'High', 'Medium', 'Low')",
                    },
                },
                "required": ["project", "summary", "description"],
            },
        ),
        Tool(
            name="update_issue",
            description="Update a JIRA issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "The issue key to update",
                    },
                    "fields": {
                        "type": "object",
                        "description": "Fields to update (e.g., {summary: 'New summary', description: 'New description'})",
                    },
                },
                "required": ["issue_key", "fields"],
            },
        ),
        Tool(
            name="list_projects",
            description="""ALWAYS CALL THIS FIRST before searching issues!

Lists all JIRA projects accessible to the user. Returns the project KEY (e.g., 'SH', 'ORALIA') and NAME (e.g., 'Sensi-Hire', 'Oralia-v2').

WORKFLOW:
1. Call list_projects to see available projects and their KEYS
2. Match the user's request to the correct project KEY
3. Use that KEY in search_issues JQL: 'project = KEY'

Example: If user asks about "Sensi Hire" and list_projects shows {'key': 'SH', 'name': 'Sensi-Hire'}, use 'project = SH' in JQL.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_project",
            description="Get detailed information about a specific JIRA project including its description and lead",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "The project key (e.g., 'PROJ', 'KAAY'). Get this from list_projects first.",
                    },
                },
                "required": ["project_key"],
            },
        ),
        Tool(
            name="add_comment",
            description="Add a comment to an issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "The issue key",
                    },
                    "comment": {
                        "type": "string",
                        "description": "The comment text",
                    },
                },
                "required": ["issue_key", "comment"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls with proper error handling."""
    try:
        if name == "search_issues":
            return await handle_search_issues(arguments)
        elif name == "get_issue":
            return await handle_get_issue(arguments)
        elif name == "create_issue":
            return await handle_create_issue(arguments)
        elif name == "update_issue":
            return await handle_update_issue(arguments)
        elif name == "list_projects":
            return await handle_list_projects()
        elif name == "get_project":
            return await handle_get_project(arguments)
        elif name == "add_comment":
            return await handle_add_comment(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except JIRAError as e:
        return handle_jira_error(e, name)
    except Exception as e:
        return handle_jira_error(e, name)


async def handle_search_issues(arguments: dict[str, Any]) -> list[TextContent]:
    """Search for issues using JQL."""
    # Validate required parameters with clear error messages
    if "jql" not in arguments or not arguments["jql"]:
        return [TextContent(
            type="text",
            text='ERROR: Missing required parameter "jql". You MUST provide a JQL query string.\n\n' +
                 'Examples of valid calls:\n' +
                 '- {"jql": "project = ORALIA AND status != Closed"}\n' +
                 '- {"jql": "assignee ~ \\"austin\\""}\n' +
                 '- {"jql": "status = Open"}\n\n' +
                 'NEVER call search_issues with empty parameters {}!'
        )]

    client = get_jira_client()

    jql = arguments["jql"]
    max_results = arguments.get("max_results", 50)
    fields = arguments.get("fields", "key,summary,status,assignee")

    issues = client.search_issues(jql, maxResults=max_results, fields=fields)

    results = []
    for issue in issues:
        issue_data = {
            "key": issue.key,
            "summary": issue.fields.summary,
            "status": issue.fields.status.name,
        }
        if hasattr(issue.fields, "assignee") and issue.fields.assignee:
            issue_data["assignee"] = issue.fields.assignee.displayName

        results.append(issue_data)

    result = {
        "jql": jql,
        "total": len(results),
        "issues": results,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_issue(arguments: dict[str, Any]) -> list[TextContent]:
    """Get detailed issue information."""
    client = get_jira_client()

    issue_key = arguments["issue_key"]
    issue = client.issue(issue_key)

    result = {
        "key": issue.key,
        "summary": issue.fields.summary,
        "description": issue.fields.description,
        "status": issue.fields.status.name,
        "priority": issue.fields.priority.name if issue.fields.priority else None,
        "created": issue.fields.created,
        "updated": issue.fields.updated,
        "reporter": issue.fields.reporter.displayName,
        "assignee": issue.fields.assignee.displayName if issue.fields.assignee else None,
        "labels": issue.fields.labels,
        "comments": [
            {"author": comment.author.displayName, "body": comment.body, "created": comment.created}
            for comment in issue.fields.comment.comments
        ],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_create_issue(arguments: dict[str, Any]) -> list[TextContent]:
    """Create a new issue."""
    client = get_jira_client()

    project = arguments["project"]
    summary = arguments["summary"]
    description = arguments["description"]
    issue_type = arguments.get("issue_type", "Task")
    priority = arguments.get("priority")

    issue_dict = {
        "project": {"key": project},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type},
    }

    if priority:
        issue_dict["priority"] = {"name": priority}

    new_issue = client.create_issue(fields=issue_dict)

    result = {
        "key": new_issue.key,
        "summary": summary,
        "url": f"{client.server_url}/browse/{new_issue.key}",
        "status": "created",
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_update_issue(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing issue."""
    client = get_jira_client()

    issue_key = arguments["issue_key"]
    fields = arguments["fields"]

    issue = client.issue(issue_key)
    issue.update(fields=fields)

    result = {
        "key": issue_key,
        "updated_fields": list(fields.keys()),
        "status": "updated",
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_list_projects() -> list[TextContent]:
    """List all projects."""
    client = get_jira_client()

    projects = client.projects()

    results = [
        {
            "key": project.key,
            "name": project.name,
            "lead": project.lead.displayName if hasattr(project, "lead") else None,
        }
        for project in projects
    ]

    result = {
        "count": len(results),
        "projects": results,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_project(arguments: dict[str, Any]) -> list[TextContent]:
    """Get project details."""
    # Validate required parameters with clear error messages
    if "project_key" not in arguments or not arguments["project_key"]:
        return [TextContent(
            type="text",
            text='ERROR: Missing required parameter "project_key". You MUST provide a project key.\n\n' +
                 'IMPORTANT: You need to call list_projects FIRST to get the available project keys!\n\n' +
                 'Example workflow:\n' +
                 '1. Call list_projects with {} to see all projects\n' +
                 '2. Find the project key (e.g., "ORALIA" for "oralia-v2")\n' +
                 '3. Call get_project with {"project_key": "ORALIA"}\n\n' +
                 'NEVER call get_project with empty parameters {}!'
        )]

    client = get_jira_client()

    project_key = arguments["project_key"]
    project = client.project(project_key)

    result = {
        "key": project.key,
        "name": project.name,
        "description": project.description if hasattr(project, "description") else None,
        "lead": project.lead.displayName if hasattr(project, "lead") else None,
        "url": project.self,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_add_comment(arguments: dict[str, Any]) -> list[TextContent]:
    """Add a comment to an issue."""
    client = get_jira_client()

    issue_key = arguments["issue_key"]
    comment_text = arguments["comment"]

    comment = client.add_comment(issue_key, comment_text)

    result = {
        "issue_key": issue_key,
        "comment_id": comment.id,
        "author": comment.author.displayName,
        "created": comment.created,
        "status": "added",
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


def main():
    """Run the JIRA MCP server."""
    import asyncio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()

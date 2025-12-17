#!/usr/bin/env python3
"""
JIRA MCP Server

Provides MCP tools for interacting with JIRA issues and projects.
"""

import json
import logging
import os
from typing import Any

from jira import JIRA
from jira.exceptions import JIRAError
from mcp.server import Server
from mcp.types import Tool, TextContent

from query_parser import JiraQueryParser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jira-mcp-server")

# Get JIRA URL and ensure it has a scheme
jira_url = os.getenv("JIRA_URL", "")
if jira_url and not jira_url.startswith(("http://", "https://")):
    jira_url = f"https://{jira_url}"
    logger.info(f"Added https:// scheme to JIRA URL: {jira_url}")

# Initialize JIRA client
jira_client = JIRA(
    server=jira_url,
    basic_auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN")),
)

# Initialize query parser
query_parser = JiraQueryParser(jira_client)

# Create MCP server
app = Server("jira-connector")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available JIRA tools."""
    return [
        Tool(
            name="query_jira",
            description="""RECOMMENDED: Query JIRA using natural language.

This tool automatically:
- Matches person names (e.g., "austin" → "Austin Prabu")
- Matches project names (e.g., "oralia-v2" → project key "ORALIA")
- Handles status filters ("open issues", "closed", "in progress")
- Detects counts ("how many issues")
- Generates and executes the correct JQL query

Examples:
- "What is austin working on in Oralia-v2?"
- "How many open bugs are there?"
- "Show me santosh's tasks"
- "What's in the backlog?"

Just pass the user's question as-is to this tool!""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query about JIRA issues",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_issues",
            description="""Search for JIRA issues using JQL (JIRA Query Language).

Common JQL examples:
- Count open issues: 'status = Open' or 'status != Closed'
- Issues by assignee: 'assignee = "John Doe"' or 'assignee in (user1, user2)'
- Issues by project: 'project = PROJECTKEY'
- Multiple conditions: 'project = PROJ AND status = "In Progress" AND assignee = currentUser()'
- Recent updates: 'updated >= -7d' (last 7 days)
- By priority: 'priority = High'
- Unassigned: 'assignee is EMPTY'

Always start with 'project = PROJECTKEY' if you know the project.""",
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
            description="List all JIRA projects accessible to the user. Use this FIRST to discover available project keys before searching for issues.",
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
    """Handle tool calls."""
    try:
        if name == "query_jira":
            return await handle_query_jira(arguments)
        elif name == "search_issues":
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
        logger.error(f"JIRA error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"JIRA Error: {str(e)}")]
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


async def handle_query_jira(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle natural language JIRA queries."""
    if "query" not in arguments or not arguments["query"]:
        return [TextContent(
            type="text",
            text='ERROR: Missing required parameter "query". Provide a natural language query about JIRA issues.'
        )]

    query = arguments["query"]
    logger.info(f"Processing natural language query: {query}")

    # Parse the query
    parsed = query_parser.parse(query)
    logger.info(f"Parsed query: {json.dumps(parsed, indent=2)}")

    jql = parsed["jql"]
    is_count = parsed["is_count"]
    is_schedule_query = parsed.get("is_schedule_query", False)
    person_not_found = parsed.get("person_not_found")
    matched_entities = parsed["matched_entities"]

    # If a person was mentioned but not found, return an error message
    if person_not_found:
        # Get list of available assignees for suggestions
        try:
            available_assignees = query_parser._get_assignees()
            # Find similar names
            from difflib import get_close_matches
            similar = get_close_matches(person_not_found.lower(),
                                        [a.split()[0].lower() for a in available_assignees],
                                        n=5, cutoff=0.4)
            suggestions = []
            for s in similar:
                for a in available_assignees:
                    if a.split()[0].lower() == s:
                        suggestions.append(a)
                        break
        except Exception:
            suggestions = []

        response = {
            "error": f"Person '{person_not_found}' not found in JIRA",
            "query": query,
            "person_searched": person_not_found,
            "suggestions": suggestions[:5] if suggestions else [],
            "hint": "Try using their full name as it appears in JIRA, or check if they have any assigned issues.",
        }
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    # Execute the JQL query - include duedate and project for better analysis
    max_results = 50 if not is_count else 100
    fields = "key,summary,status,assignee,duedate,project"
    issues = jira_client.search_issues(jql, maxResults=max_results, fields=fields)

    # Format results
    results = []
    for issue in issues:
        issue_data = {
            "key": issue.key,
            "summary": issue.fields.summary,
            "status": issue.fields.status.name,
            "project": issue.fields.project.key if hasattr(issue.fields, "project") and issue.fields.project else None,
            "url": f"{jira_client.server_url}/browse/{issue.key}",
        }
        if hasattr(issue.fields, "assignee") and issue.fields.assignee:
            issue_data["assignee"] = issue.fields.assignee.displayName
        if hasattr(issue.fields, "duedate") and issue.fields.duedate:
            issue_data["duedate"] = issue.fields.duedate
        results.append(issue_data)

    # Build response with additional context for schedule queries
    response = {
        "query": query,
        "jql": jql,
        "matched_entities": matched_entities,
        "total": len(results),
        "is_schedule_analysis": is_schedule_query,
        "issues": results,
    }

    # Add schedule summary if this was a schedule query
    if is_schedule_query and results:
        projects_affected = {}
        for issue in results:
            proj = issue.get("project", "Unknown")
            if proj not in projects_affected:
                projects_affected[proj] = []
            projects_affected[proj].append(issue["key"])
        response["schedule_summary"] = {
            "overdue_count": len(results),
            "projects_affected": {k: len(v) for k, v in projects_affected.items()},
            "issues_by_project": projects_affected,
        }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


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

    jql = arguments["jql"]
    max_results = arguments.get("max_results", 50)
    fields = arguments.get("fields", "key,summary,status,assignee")

    issues = jira_client.search_issues(jql, maxResults=max_results, fields=fields)

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
    issue_key = arguments["issue_key"]
    issue = jira_client.issue(issue_key)

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

    new_issue = jira_client.create_issue(fields=issue_dict)

    result = {
        "key": new_issue.key,
        "summary": summary,
        "url": f"{jira_client.server_url}/browse/{new_issue.key}",
        "status": "created",
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_update_issue(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an existing issue."""
    issue_key = arguments["issue_key"]
    fields = arguments["fields"]

    issue = jira_client.issue(issue_key)
    issue.update(fields=fields)

    result = {
        "key": issue_key,
        "updated_fields": list(fields.keys()),
        "status": "updated",
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_list_projects() -> list[TextContent]:
    """List all projects."""
    projects = jira_client.projects()

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

    project_key = arguments["project_key"]
    project = jira_client.project(project_key)

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
    issue_key = arguments["issue_key"]
    comment_text = arguments["comment"]

    comment = jira_client.add_comment(issue_key, comment_text)

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

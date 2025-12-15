"""
JIRA connector configuration.

Provides MCP tools for interacting with JIRA:
- Querying issues with natural language
- Project management
- Issue creation and updates
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class JiraConnector(BaseConnector):
    """JIRA connector configuration."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="jira",
            name="JIRA",
            description="Manage JIRA issues and projects",
            icon="jira",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        return [
            CredentialField(
                name="jira_url",
                env_var="JIRA_URL",
                display_name="JIRA URL",
                description="Your JIRA instance URL (e.g., yourcompany.atlassian.net)",
                required=True,
                sensitive=False,
            ),
            CredentialField(
                name="jira_email",
                env_var="JIRA_EMAIL",
                display_name="Email",
                description="Your JIRA account email",
                required=True,
                sensitive=False,
            ),
            CredentialField(
                name="jira_api_token",
                env_var="JIRA_API_TOKEN",
                display_name="API Token",
                description="JIRA API token from https://id.atlassian.com/manage-profile/security/api-tokens",
                required=True,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/jira/src/jira_server.py"

    @property
    def prewarm_on_startup(self) -> bool:
        return True

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "list_projects",
            "get_project",
            "search_issues",
            "get_issue",
            "query_jira",
        ]

    @property
    def system_prompt_addition(self) -> str:
        return """
JIRA TOOLS - COMPREHENSIVE GUIDE:

**PRIMARY TOOLS:**
- `query_jira(query)` - **USE THIS FIRST** - Natural language JIRA queries. Handles names, projects, statuses.
- `list_projects()` - List ALL projects in the JIRA instance
- `search_issues(jql)` - Advanced JQL search for precise queries
- `get_issue(issue_key)` - Get details of a specific issue (e.g., "PROJ-123")
- `get_project(project_key)` - Get project details

**CRITICAL RULES - NEVER VIOLATE:**
1. ALWAYS use `query_jira()` for natural language questions - it's smart!
2. NEVER say "I can't find" without calling query_jira first
3. NEVER say "I don't have access" without trying tools
4. If query_jira returns results, SHOW THEM ALL
5. Person names work directly: "Austin", "Akash", etc.

**WORKFLOW EXAMPLES:**

"What is [person] working on?":
→ query_jira(query="What is [person] working on?")
→ Display ALL issues assigned to them

"Show me bugs" or "Open issues":
→ query_jira(query="open bugs") or query_jira(query="open issues")
→ Display ALL matching issues with details

"What projects exist?":
→ list_projects()
→ Show ALL projects with keys and names

"Sprint status" or "Current sprint":
→ query_jira(query="current sprint issues")
→ Display sprint board status

"Issues in [project]":
→ query_jira(query="issues in [project]")
→ Display ALL issues

**SMART FEATURES:**
- query_jira understands first names (Austin → Austin Prabu)
- query_jira understands project nicknames
- query_jira handles status words (open, closed, in progress)
- query_jira can count ("how many bugs?")

**NEVER DO THIS:**
- Don't say "specify a project" - query_jira figures it out
- Don't ask for JQL - convert natural language to query_jira call
- Don't give up if first query returns nothing - try alternative wording
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common JIRA queries."""
        message_lower = message.lower().strip()

        # List projects
        if any(kw in message_lower for kw in ["project", "projects", "list project", "show project", "what project"]):
            return [{"tool": "list_projects", "args": {}}]

        # Any question about work/issues/tasks - use query_jira directly
        if any(kw in message_lower for kw in [
            "working on", "assigned", "issue", "task", "sprint", "backlog",
            "bug", "story", "ticket", "open", "closed", "status", "who"
        ]):
            return [{"tool": "query_jira", "args": {"query": message}}]

        return None


# Export singleton instance
jira_connector = JiraConnector()

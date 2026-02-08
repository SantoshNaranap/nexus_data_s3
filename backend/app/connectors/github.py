"""
GitHub connector configuration.

Uses the OFFICIAL GitHub MCP Server from:
https://github.com/github/github-mcp-server

Provides MCP tools for interacting with GitHub:
- Repositories
- Issues
- Pull requests
- Code search
- Actions
- And more
"""

from typing import Dict, List, Optional, Any, Tuple

from .base import BaseConnector, ConnectorMetadata, CredentialField


class GitHubConnector(BaseConnector):
    """GitHub connector using official GitHub MCP Server via Docker."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="github",
            name="GitHub",
            description="Manage GitHub repositories, issues, pull requests, and code",
            icon="github",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        # OAuth flow stores token as "github_token" (via user_oauth_service.py)
        # but the official GitHub MCP server expects GITHUB_PERSONAL_ACCESS_TOKEN
        # as an environment variable. This mapping bridges that gap.
        return [
            CredentialField(
                name="github_token",  # Matches user_oauth_service.py storage key
                env_var="GITHUB_PERSONAL_ACCESS_TOKEN",  # What Docker expects
                display_name="Access Token",
                description="GitHub OAuth access token or Personal Access Token",
                required=True,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        # Not used - we override get_server_command() to use Docker
        return ""

    def get_server_command(self) -> Tuple[str, List[str]]:
        """
        Use the official GitHub MCP server via Docker.

        Docker image: ghcr.io/github/github-mcp-server
        Transport: stdio (via docker run -i)

        Note: Environment variables (like GITHUB_PERSONAL_ACCESS_TOKEN) are
        automatically injected by mcp_service._inject_docker_env_vars()
        """
        return "docker", [
            "run",
            "-i",           # Interactive mode for stdio
            "--rm",         # Remove container when done
            "ghcr.io/github/github-mcp-server"
        ]

    @property
    def cacheable_tools(self) -> List[str]:
        # Official GitHub MCP Server tool names (v0.29.0)
        return [
            "get_me",
            "get_file_contents",
            "search_repositories",
            "search_issues",
            "search_code",
            "search_pull_requests",
            "issue_read",
            "list_issues",
            "pull_request_read",
            "list_pull_requests",
            "list_branches",
            "list_commits",
        ]

    @property
    def system_prompt_addition(self) -> str:
        return """
GITHUB TOOLS (Official GitHub MCP Server v0.29.0):

**USER/ACCOUNT TOOLS:**
- `get_me` - Get current authenticated user info (login, repos count, etc.)

**REPOSITORY TOOLS:**
- `search_repositories(query)` - Search for repositories (use "user:USERNAME" to find user's repos)
- `get_file_contents(owner, repo, path, [branch])` - Get contents of a file
- `create_repository(name, description, private)` - Create a new repo
- `fork_repository(owner, repo)` - Fork a repository
- `list_branches(owner, repo)` - List branches in a repo
- `list_commits(owner, repo, [sha])` - List commits

**ISSUE TOOLS:**
- `list_issues(owner, repo, [state], [labels], [assignee])` - List issues
- `issue_read(owner, repo, issue_number)` - Get issue details
- `issue_write(owner, repo, title, body)` - Create a new issue
- `search_issues(query)` - Search issues across repos
- `add_issue_comment(owner, repo, issue_number, body)` - Add comment

**PULL REQUEST TOOLS:**
- `list_pull_requests(owner, repo, [state], [head], [base])` - List PRs
- `pull_request_read(owner, repo, pull_number)` - Get PR details
- `create_pull_request(owner, repo, title, body, head, base)` - Create PR
- `search_pull_requests(query)` - Search PRs across repos

**CODE TOOLS:**
- `search_code(query)` - Search code across repositories
- `push_files(owner, repo, branch, files, message)` - Push multiple files

**CRITICAL RULES - ZERO TOLERANCE FOR HALLUCINATION:**
1. NEVER invent, fabricate, or guess repository names, issues, or any GitHub data
2. You MUST call the actual tools and ONLY report data from tool responses
3. If you only have `get_me` result, you MUST call `search_repositories` to get actual repos
4. If a tool fails or returns no data, say "I couldn't retrieve the data" - DO NOT make up results
5. Every repository name, issue, PR you mention MUST come from an actual tool response
6. NEVER construct GitHub URLs yourself - ONLY use URLs from tool responses (html_url field)
7. If you need to show a repo link, use the EXACT html_url from the tool response

**WORKFLOW - MANDATORY STEPS:**

"Show my repos" or "what projects do I have":
1. FIRST: Call `get_me` to get the user's login name
2. THEN: Call `search_repositories(query="user:LOGIN")` with the actual login from step 1
3. ONLY display repositories that appear in the search_repositories response
4. If search_repositories wasn't called, DO NOT list any repositories

"Open issues in [repo]":
→ list_issues(owner="...", repo="...", state="open")
→ Display issue numbers, titles, and authors

"Search for code about [topic]":
→ search_code(query="[topic]")
→ Show matching files and code snippets
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common GitHub queries."""
        # NOTE: "my repos" / "what projects" queries are NOT direct routed
        # They require multi-step workflow (get_me → search_repositories)
        # Let Claude handle these with full tool access to avoid hallucination
        return None


# Export singleton instance
github_connector = GitHubConnector()

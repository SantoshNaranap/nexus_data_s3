"""
GitHub connector configuration.

Provides MCP tools for interacting with GitHub:
- Repositories
- Issues
- Pull requests
- Code
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class GitHubConnector(BaseConnector):
    """GitHub connector configuration."""

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
        return [
            CredentialField(
                name="github_token",
                env_var="GITHUB_TOKEN",
                display_name="Personal Access Token",
                description="GitHub Personal Access Token or GitHub App token",
                required=True,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/github/src/github_server.py"

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "list_repositories",
            "get_repository",
            "list_issues",
            "get_issue",
            "list_pull_requests",
            "get_pull_request",
        ]

    @property
    def system_prompt_addition(self) -> str:
        return """
GITHUB TOOLS - COMPREHENSIVE GUIDE:

**PRIMARY TOOLS:**
- `list_repositories(type, sort)` - List ALL user's repositories
- `get_repository(owner, repo)` - Get repo details, stats, languages
- `list_issues(owner, repo, state)` - List issues. state: open, closed, all
- `get_issue(owner, repo, issue_number)` - Get full issue with comments
- `list_pull_requests(owner, repo, state)` - List PRs. state: open, closed, all
- `get_pull_request(owner, repo, pr_number)` - Get PR details with diff
- `search_code(query)` - Search code across repos
- `list_commits(owner, repo)` - List recent commits

**CRITICAL RULES - NEVER VIOLATE:**
1. ALWAYS call `list_repositories()` first if you don't know the repos
2. NEVER say "I don't have access" without trying a tool first
3. NEVER say "specify a repository" - list them and let user choose
4. ALWAYS show actual issue/PR content, not just counts
5. Use "owner/repo" format derived from list_repositories results

**WORKFLOW EXAMPLES:**

"Show my repos" or "What repositories do I have?":
→ list_repositories()
→ Display ALL repos with names, descriptions, stars, last updated

"Issues in [repo]" or "Open issues":
→ list_issues(owner, repo, state="open")
→ Display ALL issues with titles, authors, labels

"Pull requests" or "Open PRs":
→ list_pull_requests(owner, repo, state="open")
→ Display ALL PRs with titles, authors, status

"Recent activity" or "What's happening in [repo]?":
→ list_commits(owner, repo) + list_issues() + list_pull_requests()
→ Show recent commits, new issues, open PRs

"Find code that does [X]":
→ search_code(query="[X]")
→ Show matching files and code snippets

"PR #[number]" or "Issue #[number]":
→ get_pull_request() or get_issue()
→ Show FULL details with description and comments

**SMART REPO DETECTION:**
- If user says "my repo" or "the repo" → list_repositories() first
- Extract owner/repo from list_repositories results
- Most users have their repos under their own username

**DATA TO ALWAYS SHOW:**
- Repos: name, description, stars, language, last push
- Issues: number, title, author, labels, state
- PRs: number, title, author, status, mergeable

**NEVER DO THIS:**
- Don't ask "which repo?" - show the list and ask user to pick
- Don't summarize "you have 5 issues" - show the actual issues
- Don't hide code changes in PRs - show the diffs
- Don't refuse access - the token is already configured
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common GitHub queries."""
        message_lower = message.lower().strip()

        if any(kw in message_lower for kw in ["repo", "repository", "repositories"]):
            return [{"tool": "list_repositories", "args": {}}]

        # Note: Don't route issues/PRs directly without repo context
        return None


# Export singleton instance
github_connector = GitHubConnector()

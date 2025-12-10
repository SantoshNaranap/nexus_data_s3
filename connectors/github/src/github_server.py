#!/usr/bin/env python3
"""
GitHub MCP Server

Provides MCP tools for interacting with GitHub repositories, issues, pull requests,
and other GitHub resources using the GitHub REST API via PyGithub.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from github import Github, GithubException
from github.PullRequest import PullRequest
from github.Issue import Issue
from github.Repository import Repository
from mcp.server import Server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("github-mcp-server")

# Initialize GitHub client
github_token = os.getenv("GITHUB_TOKEN", "")
github_client = Github(github_token) if github_token else None

# Create MCP server
app = Server("github-connector")

# Cache for repository lookups
_repo_cache: dict = {}


def _get_repo(repo_name: str) -> Optional[Repository]:
    """Get repository by name with caching."""
    if repo_name in _repo_cache:
        return _repo_cache[repo_name]

    try:
        repo = github_client.get_repo(repo_name)
        _repo_cache[repo_name] = repo
        return repo
    except GithubException as e:
        logger.error(f"Error getting repository {repo_name}: {e}")
        return None


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime to readable string."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_issue(issue: Issue) -> dict:
    """Format issue object to dict."""
    return {
        "number": issue.number,
        "title": issue.title,
        "state": issue.state,
        "author": issue.user.login if issue.user else "Unknown",
        "created_at": _format_datetime(issue.created_at),
        "updated_at": _format_datetime(issue.updated_at),
        "labels": [label.name for label in issue.labels],
        "assignees": [a.login for a in issue.assignees],
        "comments": issue.comments,
        "url": issue.html_url,
    }


def _format_pr(pr: PullRequest) -> dict:
    """Format pull request object to dict."""
    return {
        "number": pr.number,
        "title": pr.title,
        "state": pr.state,
        "author": pr.user.login if pr.user else "Unknown",
        "created_at": _format_datetime(pr.created_at),
        "updated_at": _format_datetime(pr.updated_at),
        "merged": pr.merged,
        "merged_at": _format_datetime(pr.merged_at) if pr.merged else None,
        "base": pr.base.ref,
        "head": pr.head.ref,
        "labels": [label.name for label in pr.labels],
        "reviewers": [r.login for r in pr.requested_reviewers],
        "comments": pr.comments,
        "commits": pr.commits,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": pr.changed_files,
        "url": pr.html_url,
    }


def _format_repo(repo: Repository) -> dict:
    """Format repository object to dict."""
    return {
        "name": repo.name,
        "full_name": repo.full_name,
        "description": repo.description,
        "private": repo.private,
        "fork": repo.fork,
        "stars": repo.stargazers_count,
        "forks": repo.forks_count,
        "watchers": repo.watchers_count,
        "open_issues": repo.open_issues_count,
        "language": repo.language,
        "default_branch": repo.default_branch,
        "created_at": _format_datetime(repo.created_at),
        "updated_at": _format_datetime(repo.updated_at),
        "url": repo.html_url,
    }


# ============================================================================
# MCP Tool Definitions
# ============================================================================

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available GitHub tools."""
    return [
        Tool(
            name="list_repositories",
            description="List repositories for a user or organization. Can filter by type (all, owner, member, public, private).",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Username or organization name. Leave empty for authenticated user's repos."
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by type: all, owner, member, public, private",
                        "enum": ["all", "owner", "member", "public", "private"],
                        "default": "all"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of repos to return",
                        "default": 30
                    }
                }
            }
        ),
        Tool(
            name="get_repository",
            description="Get detailed information about a specific repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="list_issues",
            description="List issues in a repository. Can filter by state, labels, assignee, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "state": {
                        "type": "string",
                        "description": "Filter by state: open, closed, all",
                        "enum": ["open", "closed", "all"],
                        "default": "open"
                    },
                    "labels": {
                        "type": "string",
                        "description": "Comma-separated list of label names"
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Filter by assignee username"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of issues to return",
                        "default": 30
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_issue",
            description="Get detailed information about a specific issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue number"
                    }
                },
                "required": ["repo", "issue_number"]
            }
        ),
        Tool(
            name="create_issue",
            description="Create a new issue in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "title": {
                        "type": "string",
                        "description": "Issue title"
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue body/description"
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of label names"
                    },
                    "assignees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of usernames to assign"
                    }
                },
                "required": ["repo", "title"]
            }
        ),
        Tool(
            name="list_pull_requests",
            description="List pull requests in a repository. Can filter by state, base branch, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "state": {
                        "type": "string",
                        "description": "Filter by state: open, closed, all",
                        "enum": ["open", "closed", "all"],
                        "default": "open"
                    },
                    "base": {
                        "type": "string",
                        "description": "Filter by base branch name"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of PRs to return",
                        "default": 30
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_pull_request",
            description="Get detailed information about a specific pull request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "Pull request number"
                    }
                },
                "required": ["repo", "pr_number"]
            }
        ),
        Tool(
            name="get_pr_diff",
            description="Get the diff/changes for a pull request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "Pull request number"
                    }
                },
                "required": ["repo", "pr_number"]
            }
        ),
        Tool(
            name="list_commits",
            description="List commits in a repository or on a specific branch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch name (defaults to default branch)"
                    },
                    "author": {
                        "type": "string",
                        "description": "Filter by author username or email"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of commits to return",
                        "default": 30
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_file_content",
            description="Get the contents of a file from a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to the file in the repository"
                    },
                    "ref": {
                        "type": "string",
                        "description": "Branch, tag, or commit SHA (defaults to default branch)"
                    }
                },
                "required": ["repo", "path"]
            }
        ),
        Tool(
            name="search_code",
            description="Search for code across GitHub repositories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. Can include qualifiers like 'repo:', 'language:', 'path:'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 30
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_issues",
            description="Search for issues and pull requests across GitHub.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. Can include qualifiers like 'repo:', 'is:issue', 'is:pr', 'state:', 'author:'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 30
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_branches",
            description="List branches in a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of branches to return",
                        "default": 30
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_workflow_runs",
            description="List recent GitHub Actions workflow runs for a repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "workflow": {
                        "type": "string",
                        "description": "Workflow file name or ID (optional)"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status: completed, in_progress, queued",
                        "enum": ["completed", "in_progress", "queued"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of runs to return",
                        "default": 10
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="add_issue_comment",
            description="Add a comment to an issue or pull request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository name in format 'owner/repo'"
                    },
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue or PR number"
                    },
                    "body": {
                        "type": "string",
                        "description": "Comment body"
                    }
                },
                "required": ["repo", "issue_number", "body"]
            }
        ),
        Tool(
            name="get_user_info",
            description="Get information about a GitHub user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "GitHub username. Leave empty for authenticated user."
                    }
                }
            }
        ),
    ]


# ============================================================================
# Tool Implementations
# ============================================================================

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if not github_client:
        return [TextContent(
            type="text",
            text=json.dumps({"error": "GitHub token not configured. Please set GITHUB_TOKEN."})
        )]

    try:
        result = await _execute_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except GithubException as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"GitHub API error: {e.data.get('message', str(e))}"})
        )]
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def _execute_tool(name: str, args: dict) -> Any:
    """Execute a specific tool."""

    if name == "list_repositories":
        owner = args.get("owner")
        repo_type = args.get("type", "all")
        limit = args.get("limit", 30)

        if owner:
            try:
                user = github_client.get_user(owner)
                repos = list(user.get_repos(type=repo_type))[:limit]
            except GithubException:
                org = github_client.get_organization(owner)
                repos = list(org.get_repos(type=repo_type))[:limit]
        else:
            user = github_client.get_user()
            repos = list(user.get_repos(type=repo_type))[:limit]

        return {
            "repositories": [_format_repo(r) for r in repos],
            "count": len(repos)
        }

    elif name == "get_repository":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}
        return _format_repo(repo)

    elif name == "list_issues":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        state = args.get("state", "open")
        labels = args.get("labels", "").split(",") if args.get("labels") else []
        assignee = args.get("assignee")
        limit = args.get("limit", 30)

        kwargs = {"state": state}
        if labels:
            kwargs["labels"] = [l.strip() for l in labels if l.strip()]
        if assignee:
            kwargs["assignee"] = assignee

        issues = list(repo.get_issues(**kwargs))[:limit]
        # Filter out PRs (they appear as issues too)
        issues = [i for i in issues if not i.pull_request]

        return {
            "issues": [_format_issue(i) for i in issues],
            "count": len(issues)
        }

    elif name == "get_issue":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        issue = repo.get_issue(args["issue_number"])
        result = _format_issue(issue)
        result["body"] = issue.body
        return result

    elif name == "create_issue":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        kwargs = {"title": args["title"]}
        if args.get("body"):
            kwargs["body"] = args["body"]
        if args.get("labels"):
            kwargs["labels"] = args["labels"]
        if args.get("assignees"):
            kwargs["assignees"] = args["assignees"]

        issue = repo.create_issue(**kwargs)
        return {
            "success": True,
            "issue": _format_issue(issue),
            "url": issue.html_url
        }

    elif name == "list_pull_requests":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        state = args.get("state", "open")
        base = args.get("base")
        limit = args.get("limit", 30)

        kwargs = {"state": state}
        if base:
            kwargs["base"] = base

        prs = list(repo.get_pulls(**kwargs))[:limit]

        return {
            "pull_requests": [_format_pr(pr) for pr in prs],
            "count": len(prs)
        }

    elif name == "get_pull_request":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        pr = repo.get_pull(args["pr_number"])
        result = _format_pr(pr)
        result["body"] = pr.body
        return result

    elif name == "get_pr_diff":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        pr = repo.get_pull(args["pr_number"])
        files = list(pr.get_files())

        return {
            "pr_number": pr.number,
            "title": pr.title,
            "files_changed": len(files),
            "additions": pr.additions,
            "deletions": pr.deletions,
            "files": [
                {
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "patch": f.patch[:2000] if f.patch else None  # Truncate large patches
                }
                for f in files[:50]  # Limit to 50 files
            ]
        }

    elif name == "list_commits":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        branch = args.get("branch", repo.default_branch)
        author = args.get("author")
        limit = args.get("limit", 30)

        kwargs = {"sha": branch}
        if author:
            kwargs["author"] = author

        commits = list(repo.get_commits(**kwargs))[:limit]

        return {
            "commits": [
                {
                    "sha": c.sha[:7],
                    "message": c.commit.message.split("\n")[0],  # First line only
                    "author": c.commit.author.name if c.commit.author else "Unknown",
                    "date": _format_datetime(c.commit.author.date) if c.commit.author else "N/A",
                    "url": c.html_url
                }
                for c in commits
            ],
            "count": len(commits)
        }

    elif name == "get_file_content":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        path = args["path"]
        ref = args.get("ref", repo.default_branch)

        try:
            content = repo.get_contents(path, ref=ref)
            if isinstance(content, list):
                # It's a directory
                return {
                    "type": "directory",
                    "path": path,
                    "contents": [
                        {"name": c.name, "type": c.type, "path": c.path}
                        for c in content
                    ]
                }
            else:
                # It's a file
                decoded = content.decoded_content.decode("utf-8")
                # Truncate very large files
                if len(decoded) > 50000:
                    decoded = decoded[:50000] + "\n\n... (truncated)"
                return {
                    "type": "file",
                    "path": path,
                    "size": content.size,
                    "content": decoded
                }
        except GithubException as e:
            return {"error": f"File not found: {path}"}

    elif name == "search_code":
        query = args["query"]
        limit = args.get("limit", 30)

        results = list(github_client.search_code(query))[:limit]

        return {
            "results": [
                {
                    "repository": r.repository.full_name,
                    "path": r.path,
                    "name": r.name,
                    "url": r.html_url
                }
                for r in results
            ],
            "count": len(results)
        }

    elif name == "search_issues":
        query = args["query"]
        limit = args.get("limit", 30)

        results = list(github_client.search_issues(query))[:limit]

        return {
            "results": [
                {
                    "repository": r.repository.full_name if r.repository else "Unknown",
                    "number": r.number,
                    "title": r.title,
                    "state": r.state,
                    "is_pr": r.pull_request is not None,
                    "author": r.user.login if r.user else "Unknown",
                    "created_at": _format_datetime(r.created_at),
                    "url": r.html_url
                }
                for r in results
            ],
            "count": len(results)
        }

    elif name == "list_branches":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        limit = args.get("limit", 30)
        branches = list(repo.get_branches())[:limit]

        return {
            "branches": [
                {
                    "name": b.name,
                    "protected": b.protected,
                    "sha": b.commit.sha[:7]
                }
                for b in branches
            ],
            "default_branch": repo.default_branch,
            "count": len(branches)
        }

    elif name == "get_workflow_runs":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        workflow = args.get("workflow")
        status = args.get("status")
        limit = args.get("limit", 10)

        kwargs = {}
        if status:
            kwargs["status"] = status

        if workflow:
            wf = repo.get_workflow(workflow)
            runs = list(wf.get_runs(**kwargs))[:limit]
        else:
            runs = list(repo.get_workflow_runs(**kwargs))[:limit]

        return {
            "workflow_runs": [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status,
                    "conclusion": r.conclusion,
                    "branch": r.head_branch,
                    "event": r.event,
                    "created_at": _format_datetime(r.created_at),
                    "url": r.html_url
                }
                for r in runs
            ],
            "count": len(runs)
        }

    elif name == "add_issue_comment":
        repo = _get_repo(args["repo"])
        if not repo:
            return {"error": f"Repository {args['repo']} not found"}

        issue = repo.get_issue(args["issue_number"])
        comment = issue.create_comment(args["body"])

        return {
            "success": True,
            "comment_id": comment.id,
            "url": comment.html_url
        }

    elif name == "get_user_info":
        username = args.get("username")

        if username:
            user = github_client.get_user(username)
        else:
            user = github_client.get_user()

        return {
            "login": user.login,
            "name": user.name,
            "bio": user.bio,
            "company": user.company,
            "location": user.location,
            "email": user.email,
            "public_repos": user.public_repos,
            "followers": user.followers,
            "following": user.following,
            "created_at": _format_datetime(user.created_at),
            "url": user.html_url
        }

    else:
        return {"error": f"Unknown tool: {name}"}


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

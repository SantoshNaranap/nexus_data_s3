"""Response formatting for various datasources."""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Formats tool results into human-readable responses."""

    def format_ultra_fast_response(
        self, datasource: str, tool_name: str, result: str
    ) -> Optional[str]:
        """
        Format tool results directly without Claude (ultra-fast path).
        Returns None if formatting not possible.
        """
        try:
            data = json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return None

        if datasource == "s3" and tool_name == "list_buckets":
            return self._format_s3_buckets(data)

        if datasource == "jira" and tool_name == "list_projects":
            return self._format_jira_projects(data)

        if datasource == "mysql" and tool_name == "list_tables":
            return self._format_mysql_tables(data)

        if datasource == "mysql" and tool_name == "describe_table":
            return self._format_mysql_table_schema(data)

        if datasource == "mysql" and tool_name == "execute_query":
            return self._format_mysql_query_results(data)

        if datasource == "slack" and tool_name == "list_channels":
            return self._format_slack_channels(data)

        if datasource == "slack" and tool_name == "list_users":
            return self._format_slack_users(data)

        if datasource == "github" and tool_name == "list_repositories":
            return self._format_github_repos(data)

        if datasource == "github" and tool_name == "list_issues":
            return self._format_github_issues(data)

        if datasource == "github" and tool_name == "list_pull_requests":
            return self._format_github_prs(data)

        return None

    def _format_s3_buckets(self, data: dict) -> str:
        """Format S3 bucket list response."""
        buckets = data.get("buckets", [])
        if not buckets:
            return "No S3 buckets found in your account."

        response = f"## Your S3 Buckets ({len(buckets)} found)\n\n"
        response += "| Bucket Name | Created |\n"
        response += "|------------|--------|\n"
        for bucket in buckets:
            name = bucket.get("name", "Unknown")
            created = bucket.get("creation_date", "Unknown")[:10] if bucket.get("creation_date") else "Unknown"
            response += f"| {name} | {created} |\n"
        return response

    def _format_jira_projects(self, data: dict) -> str:
        """Format JIRA projects list response."""
        projects = data.get("projects", [])
        if not projects:
            return "No JIRA projects found."

        response = f"## Your JIRA Projects ({len(projects)} found)\n\n"
        response += "| Key | Name | Type |\n"
        response += "|-----|------|------|\n"
        for proj in projects[:15]:  # Limit to first 15
            key = proj.get("key", "")
            name = proj.get("name", "")[:40]  # Truncate long names
            ptype = proj.get("type", proj.get("projectTypeKey", ""))
            response += f"| {key} | {name} | {ptype} |\n"

        if len(projects) > 15:
            response += f"\n*...and {len(projects) - 15} more projects*"
        return response

    def _format_mysql_tables(self, data: dict) -> str:
        """Format MySQL tables list response."""
        tables = data.get("tables", [])
        if not tables:
            return "No tables found in the database."

        response = f"## Database Tables ({len(tables)} found)\n\n"
        for table in tables:
            response += f"- `{table}`\n"
        return response

    def _format_mysql_table_schema(self, data: dict) -> str:
        """Format MySQL table schema response."""
        columns = data.get("columns", [])
        table_name = data.get("table", "Unknown")

        if not columns:
            return f"No schema information found for table `{table_name}`."

        response = f"## Schema for `{table_name}`\n\n"
        response += "| Column | Type | Nullable | Key | Default |\n"
        response += "|--------|------|----------|-----|--------|\n"
        for col in columns:
            name = col.get("name", "")
            col_type = col.get("type", "")
            nullable = "Yes" if col.get("nullable") else "No"
            key = col.get("key", "")
            default = col.get("default", "NULL")
            response += f"| {name} | {col_type} | {nullable} | {key} | {default} |\n"
        return response

    def _format_mysql_query_results(self, data: dict) -> str:
        """Format MySQL query results response."""
        rows = data.get("rows", [])
        row_count = data.get("row_count", len(rows))

        if not rows:
            return "Query executed successfully. No rows returned."

        # Get column headers from first row
        if rows:
            columns = list(rows[0].keys())
        else:
            return "Query executed successfully. No data returned."

        response = f"## Query Results ({row_count} rows)\n\n"

        # Build markdown table
        response += "| " + " | ".join(columns) + " |\n"
        response += "|" + "|".join(["---" for _ in columns]) + "|\n"

        for row in rows[:50]:  # Limit to 50 rows
            values = [str(row.get(col, ""))[:50] for col in columns]  # Truncate long values
            response += "| " + " | ".join(values) + " |\n"

        if row_count > 50:
            response += f"\n*...showing 50 of {row_count} rows*"

        return response

    def _format_slack_channels(self, data: dict) -> str:
        """Format Slack channels list response."""
        channels = data.get("channels", [])
        if not channels:
            return "No Slack channels found."

        response = f"## Slack Channels ({len(channels)} found)\n\n"
        response += "| Channel | Members | Topic |\n"
        response += "|---------|---------|-------|\n"

        for ch in channels[:20]:  # Limit to first 20
            name = ch.get("name", "")
            is_private = ch.get("is_private", False)
            prefix = "🔒 " if is_private else "#"
            members = ch.get("num_members", 0)
            topic = ch.get("topic", "")[:40]  # Truncate
            response += f"| {prefix}{name} | {members} | {topic} |\n"

        if len(channels) > 20:
            response += f"\n*...and {len(channels) - 20} more channels*"
        return response

    def _format_slack_users(self, data: dict) -> str:
        """Format Slack users list response."""
        users = data.get("users", [])
        if not users:
            return "No Slack users found."

        response = f"## Slack Team Members ({len(users)} found)\n\n"
        response += "| Name | Title | Status |\n"
        response += "|------|-------|--------|\n"

        for user in users[:20]:  # Limit to first 20
            name = user.get("real_name", user.get("name", ""))
            title = user.get("title", "")[:30]  # Truncate
            status = user.get("status_emoji", "") + " " + user.get("status_text", "")[:20]
            is_admin = " 👑" if user.get("is_admin") else ""
            response += f"| {name}{is_admin} | {title} | {status.strip()} |\n"

        if len(users) > 20:
            response += f"\n*...and {len(users) - 20} more team members*"
        return response

    def _format_github_repos(self, data: dict) -> str:
        """Format GitHub repositories list response."""
        repos = data.get("repositories", [])
        if not repos:
            return "No GitHub repositories found."

        response = f"## Your GitHub Repositories ({len(repos)} found)\n\n"
        response += "| Repository | Language | Stars | Issues |\n"
        response += "|------------|----------|-------|--------|\n"

        for repo in repos[:20]:  # Limit to first 20
            name = repo.get("full_name", repo.get("name", ""))[:40]
            language = repo.get("language", "-") or "-"
            stars = repo.get("stars", 0)
            issues = repo.get("open_issues", 0)
            private = " (private)" if repo.get("private") else ""
            response += f"| {name}{private} | {language} | {stars} | {issues} |\n"

        if len(repos) > 20:
            response += f"\n*...and {len(repos) - 20} more repositories*"
        return response

    def _format_github_issues(self, data: dict) -> str:
        """Format GitHub issues list response."""
        issues = data.get("issues", [])
        count = data.get("count", len(issues))
        if not issues:
            return "No issues found."

        response = f"## GitHub Issues ({count} found)\n\n"
        response += "| # | Title | State | Author | Labels |\n"
        response += "|---|-------|-------|--------|--------|\n"

        for issue in issues[:20]:
            num = issue.get("number", "?")
            title = issue.get("title", "")[:40]
            state = issue.get("state", "")
            author = issue.get("author", "")
            labels = ", ".join(issue.get("labels", [])[:3])
            response += f"| #{num} | {title} | {state} | {author} | {labels} |\n"

        if count > 20:
            response += f"\n*...and {count - 20} more issues*"
        return response

    def _format_github_prs(self, data: dict) -> str:
        """Format GitHub pull requests list response."""
        prs = data.get("pull_requests", [])
        count = data.get("count", len(prs))
        if not prs:
            return "No pull requests found."

        response = f"## GitHub Pull Requests ({count} found)\n\n"
        response += "| # | Title | State | Author | Base |\n"
        response += "|---|-------|-------|--------|------|\n"

        for pr in prs[:20]:
            num = pr.get("number", "?")
            title = pr.get("title", "")[:40]
            state = pr.get("state", "")
            author = pr.get("author", "")
            base = pr.get("base", "")
            merged = " (merged)" if pr.get("merged") else ""
            response += f"| #{num} | {title} | {state}{merged} | {author} | {base} |\n"

        if count > 20:
            response += f"\n*...and {count - 20} more pull requests*"
        return response

    def get_immediate_feedback_message(self, datasource: str, message: str) -> str:
        """Generate an immediate feedback message based on query type."""
        message_lower = message.lower()

        # Datasource-specific messages
        if datasource == "s3":
            if "bucket" in message_lower or "list" in message_lower:
                return "*Checking your S3 buckets...*"
            elif "read" in message_lower or "content" in message_lower or "file" in message_lower:
                return "*Reading document...*"
            elif "search" in message_lower:
                return "*Searching documents...*"
            return "*Connecting to S3...*"

        elif datasource == "jira":
            if "project" in message_lower:
                return "*Fetching JIRA projects...*"
            elif "sprint" in message_lower:
                return "*Loading sprint data...*"
            elif "assign" in message_lower or "working" in message_lower or "who" in message_lower:
                return "*Checking team assignments...*"
            elif "backlog" in message_lower:
                return "*Analyzing backlog...*"
            return "*Querying JIRA...*"

        elif datasource == "mysql":
            if "table" in message_lower:
                return "*Listing tables...*"
            elif "schema" in message_lower or "structure" in message_lower:
                return "*Fetching schema...*"
            return "*Querying database...*"

        elif datasource == "google_workspace":
            if "calendar" in message_lower:
                return "*Checking calendar...*"
            elif "email" in message_lower or "gmail" in message_lower:
                return "*Loading emails...*"
            elif "doc" in message_lower or "sheet" in message_lower:
                return "*Fetching documents...*"
            return "*Connecting to Google Workspace...*"

        elif datasource == "slack":
            if "channel" in message_lower:
                return "*Loading Slack channels...*"
            elif "user" in message_lower or "team" in message_lower or "who" in message_lower:
                return "*Checking team members...*"
            elif "message" in message_lower or "read" in message_lower:
                return "*Reading messages...*"
            elif "search" in message_lower or "find" in message_lower:
                return "*Searching Slack...*"
            elif "send" in message_lower or "post" in message_lower:
                return "*Sending message...*"
            return "*Connecting to Slack...*"

        elif datasource == "github":
            if "repo" in message_lower:
                return "*Loading repositories...*"
            elif "issue" in message_lower or "bug" in message_lower:
                return "*Fetching issues...*"
            elif "pr" in message_lower or "pull" in message_lower:
                return "*Loading pull requests...*"
            elif "commit" in message_lower:
                return "*Fetching commits...*"
            elif "branch" in message_lower:
                return "*Loading branches...*"
            elif "workflow" in message_lower or "action" in message_lower:
                return "*Checking CI/CD runs...*"
            elif "file" in message_lower or "code" in message_lower:
                return "*Reading file...*"
            elif "search" in message_lower:
                return "*Searching GitHub...*"
            return "*Connecting to GitHub...*"

        return "*Processing...*"

    def format_error_response(self, error: str, datasource: str) -> str:
        """Format error responses nicely."""
        return f"**Error**: {error}\n\nPlease try rephrasing your question or check your {datasource} connection."

    def format_tool_result_summary(self, tool_name: str, result: dict) -> str:
        """Generate a brief summary of a tool result."""
        if "error" in result:
            return f"Error in {tool_name}"

        # Generate context-appropriate summaries
        if "buckets" in result:
            count = len(result.get("buckets", []))
            return f"Found {count} bucket(s)"
        elif "objects" in result:
            count = len(result.get("objects", []))
            return f"Found {count} object(s)"
        elif "projects" in result:
            count = len(result.get("projects", []))
            return f"Found {count} project(s)"
        elif "issues" in result:
            count = len(result.get("issues", []))
            return f"Found {count} issue(s)"
        elif "rows" in result:
            count = result.get("row_count", len(result.get("rows", [])))
            return f"Found {count} row(s)"
        elif "tables" in result:
            count = len(result.get("tables", []))
            return f"Found {count} table(s)"

        return "Data retrieved successfully"


# Global response formatter instance
response_formatter = ResponseFormatter()

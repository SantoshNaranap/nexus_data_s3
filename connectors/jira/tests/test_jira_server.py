"""Tests for JIRA MCP Server."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_jira():
    """Mock JIRA client."""
    with patch("jira_server.jira_client") as mock:
        yield mock


@pytest.mark.asyncio
async def test_search_issues(mock_jira):
    """Test searching issues."""
    from jira_server import handle_search_issues

    # Mock issue
    issue1 = MagicMock()
    issue1.key = "PROJ-123"
    issue1.fields.summary = "Test issue"
    issue1.fields.status.name = "Open"
    issue1.fields.assignee = None

    mock_jira.search_issues.return_value = [issue1]

    arguments = {"jql": "project = PROJ", "max_results": 50}
    result = await handle_search_issues(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["total"] == 1
    assert data["issues"][0]["key"] == "PROJ-123"


@pytest.mark.asyncio
async def test_get_issue(mock_jira):
    """Test getting issue details."""
    from jira_server import handle_get_issue

    # Mock issue
    issue = MagicMock()
    issue.key = "PROJ-123"
    issue.fields.summary = "Test issue"
    issue.fields.description = "Test description"
    issue.fields.status.name = "Open"
    issue.fields.priority.name = "High"
    issue.fields.created = "2024-01-01T00:00:00"
    issue.fields.updated = "2024-01-02T00:00:00"
    issue.fields.reporter.displayName = "John Doe"
    issue.fields.assignee = None
    issue.fields.labels = ["bug"]
    issue.fields.comment.comments = []

    mock_jira.issue.return_value = issue

    arguments = {"issue_key": "PROJ-123"}
    result = await handle_get_issue(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["key"] == "PROJ-123"
    assert data["priority"] == "High"


@pytest.mark.asyncio
async def test_create_issue(mock_jira):
    """Test creating an issue."""
    from jira_server import handle_create_issue

    # Mock created issue
    new_issue = MagicMock()
    new_issue.key = "PROJ-456"
    mock_jira.create_issue.return_value = new_issue
    mock_jira.server_url = "https://test.atlassian.net"

    arguments = {
        "project": "PROJ",
        "summary": "New issue",
        "description": "Description",
        "issue_type": "Bug",
    }
    result = await handle_create_issue(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["key"] == "PROJ-456"
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_list_projects(mock_jira):
    """Test listing projects."""
    from jira_server import handle_list_projects

    # Mock projects
    project1 = MagicMock()
    project1.key = "PROJ1"
    project1.name = "Project 1"
    project1.lead.displayName = "John Doe"

    mock_jira.projects.return_value = [project1]

    result = await handle_list_projects()

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 1
    assert data["projects"][0]["key"] == "PROJ1"

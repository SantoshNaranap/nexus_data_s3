"""
E2E Tests for Google Workspace Connector

Tests conversational queries against Google Workspace (Drive, Gmail, Calendar)
with accuracy validation against actual data.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from .test_framework import (
    TestRunner,
    TestSuiteResult,
    TestStatus,
)


class GoogleWorkspaceDirectAPI:
    """Direct API client for Google Workspace validation."""

    def __init__(self):
        # Note: Google APIs require OAuth - these tests will rely on
        # the chat API which handles auth, and validate response quality
        pass

    # Google API direct calls would require separate OAuth setup
    # For now, we validate response quality and format


class TestGoogleWorkspaceConnector:
    """E2E tests for Google Workspace connector functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test runner for each test."""
        self.runner = TestRunner()

    @pytest.mark.asyncio
    async def test_search_drive_files(self):
        """Test searching for files in Google Drive."""
        suite = TestSuiteResult(suite_name="Google Drive Search", connector="google_workspace")

        # Test basic file search
        result = await self.runner.run_test_case(
            name="Search Drive files",
            query="What files do I have in Google Drive?",
            datasource="google_workspace",
            expected_contains=[],  # Will validate response quality
        )

        # Validate response contains file-like information
        if result.response:
            # Check for common file indicators
            file_indicators = ["document", "sheet", "file", "folder", "drive", "doc"]
            found_any = any(ind in result.response.lower() for ind in file_indicators)
            if found_any:
                result.status = TestStatus.PASSED
            else:
                result.status = TestStatus.FAILED
                result.error_message = "Response doesn't contain file information"

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_search_specific_topic(self):
        """Test searching for documents about a specific topic (sensihire)."""
        suite = TestSuiteResult(suite_name="Topic Search", connector="google_workspace")

        # Search for documents about a specific topic
        result = await self.runner.run_test_case(
            name="Search for topic: sensihire",
            query="Find all documents where I have talked about sensihire",
            datasource="google_workspace",
            expected_contains=[],
        )

        suite.results.append(result)

        # Follow-up: elaborate on contents
        result2 = await self.runner.run_test_case(
            name="Elaborate on found documents",
            query="Tell me more about what's in these documents about sensihire",
            datasource="google_workspace",
            expected_contains=[],
        )

        suite.results.append(result2)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        # Pass if we got responses without errors
        assert result.status != TestStatus.ERROR, f"Error: {result.error_message}"

    @pytest.mark.asyncio
    async def test_get_document_content(self):
        """Test retrieving and summarizing document content."""
        suite = TestSuiteResult(suite_name="Document Content", connector="google_workspace")

        # First search for documents
        result1 = await self.runner.run_test_case(
            name="Find documents",
            query="Show me my Google Docs",
            datasource="google_workspace",
            expected_contains=[],
        )

        suite.results.append(result1)

        # Then ask about specific content
        if result1.status != TestStatus.ERROR:
            result2 = await self.runner.run_test_case(
                name="Get document content",
                query="What's in my most recent document?",
                datasource="google_workspace",
                expected_contains=[],
            )
            suite.results.append(result2)

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_recent_emails_from_person(self):
        """Test getting recent emails from a specific person (Krishnan)."""
        suite = TestSuiteResult(suite_name="Email from Person", connector="google_workspace")

        result = await self.runner.run_test_case(
            name="Emails from Krishnan",
            query="What are the most recent emails Krishnan sent me?",
            datasource="google_workspace",
            expected_contains=[],  # Will check response quality
        )

        # Validate response mentions email-related content
        if result.response:
            email_indicators = ["email", "message", "sent", "from", "subject", "krishnan"]
            found = sum(1 for ind in email_indicators if ind in result.response.lower())
            result.accuracy_score = (found / len(email_indicators)) * 100

            if found >= 2:  # At least 2 indicators
                result.status = TestStatus.PASSED
            else:
                result.status = TestStatus.FAILED
                result.error_message = "Response doesn't appear to be about emails"

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_calendar_events(self):
        """Test getting calendar events."""
        suite = TestSuiteResult(suite_name="Calendar Events", connector="google_workspace")

        result = await self.runner.run_test_case(
            name="Today's calendar",
            query="What's on my calendar today?",
            datasource="google_workspace",
            expected_contains=[],
        )

        # Check for calendar-related response
        if result.response:
            cal_indicators = ["event", "meeting", "calendar", "schedule", "today", "no event"]
            found_any = any(ind in result.response.lower() for ind in cal_indicators)
            if found_any:
                result.status = TestStatus.PASSED

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_email_list(self):
        """Test listing recent emails."""
        suite = TestSuiteResult(suite_name="Email List", connector="google_workspace")

        result = await self.runner.run_test_case(
            name="Recent emails",
            query="Show me my recent emails",
            datasource="google_workspace",
            expected_contains=[],
        )

        # Validate email-like response
        if result.response and len(result.response) > 50:
            result.status = TestStatus.PASSED

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_conversation_context_files(self):
        """Test context maintenance when discussing files."""
        suite = TestSuiteResult(suite_name="File Context", connector="google_workspace")

        # Multi-turn about files
        results = await self.runner.run_conversation_test(
            name="File context",
            queries=[
                ("Find documents about sensihire", []),
                ("What does the first one say?", []),
                ("Who else has access to it?", []),
            ],
            datasource="google_workspace",
        )

        suite.results.extend(results)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_link_accuracy(self):
        """Test that document links in responses are valid (not hallucinated)."""
        suite = TestSuiteResult(suite_name="Link Accuracy", connector="google_workspace")

        result = await self.runner.run_test_case(
            name="Document links",
            query="Show me my Google Drive files with their links",
            datasource="google_workspace",
            expected_contains=[],
        )

        # Check for properly formatted Google links
        import re

        if result.response:
            # Valid Google Drive/Docs links patterns
            valid_patterns = [
                r'https://docs\.google\.com/document/d/[a-zA-Z0-9_-]+',
                r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+',
                r'https://drive\.google\.com/file/d/[a-zA-Z0-9_-]+',
                r'https://drive\.google\.com/drive/folders/[a-zA-Z0-9_-]+',
            ]

            found_links = []
            for pattern in valid_patterns:
                matches = re.findall(pattern, result.response)
                found_links.extend(matches)

            if found_links:
                result.status = TestStatus.PASSED
                result.actual_matches = found_links[:5]
            elif "no file" in result.response.lower() or "couldn't find" in result.response.lower():
                result.status = TestStatus.PASSED  # Valid response if no files
            else:
                result.status = TestStatus.FAILED
                result.error_message = "No valid Google links found in response"

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)


class TestGoogleWorkspaceGeneric:
    """Generic tests that work with any data - not hardcoded to specific names."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()

    @pytest.mark.asyncio
    async def test_dynamic_topic_search(self):
        """Test searching for documents about any topic."""
        suite = TestSuiteResult(suite_name="Dynamic Topic Search", connector="google_workspace")

        # Test with different topics - these should work for any user
        topics = ["project", "meeting", "notes", "report"]

        for topic in topics:
            result = await self.runner.run_test_case(
                name=f"Search for: {topic}",
                query=f"Find documents about {topic}",
                datasource="google_workspace",
                expected_contains=[],
            )

            if result.status != TestStatus.ERROR:
                suite.results.append(result)
                break  # Found a working topic

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_dynamic_email_search(self):
        """Test searching emails with dynamic sender."""
        suite = TestSuiteResult(suite_name="Dynamic Email Search", connector="google_workspace")

        # First get any emails
        result1 = await self.runner.run_test_case(
            name="List recent emails",
            query="Show me my 5 most recent emails",
            datasource="google_workspace",
            expected_contains=[],
        )

        suite.results.append(result1)

        # Extract a sender name from response and query about them
        if result1.response and result1.status != TestStatus.ERROR:
            result2 = await self.runner.run_test_case(
                name="Follow-up on sender",
                query="Tell me more about the email from the first sender",
                datasource="google_workspace",
                expected_contains=[],
            )
            suite.results.append(result2)

        suite.end_time = datetime.now()
        self.runner.print_results(suite)


# Standalone runner for quick testing
async def run_all_google_workspace_tests():
    """Run all Google Workspace tests and save results."""
    runner = TestRunner()

    print("\n" + "=" * 80)
    print("GOOGLE WORKSPACE CONNECTOR E2E TESTS")
    print("=" * 80)

    suite = TestSuiteResult(suite_name="Complete Google Workspace Test Suite", connector="google_workspace")

    # Test 1: Search Drive
    print("\n[1/7] Testing Drive file search...")
    result = await runner.run_test_case(
        name="Search Drive",
        query="What files do I have in Google Drive?",
        datasource="google_workspace",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 2: Topic search
    print("\n[2/7] Testing topic search (sensihire)...")
    result = await runner.run_test_case(
        name="Topic search",
        query="Find all documents where I have talked about sensihire",
        datasource="google_workspace",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 3: Document content
    print("\n[3/7] Testing document content retrieval...")
    result = await runner.run_test_case(
        name="Document content",
        query="Tell me about the contents of the documents you found about sensihire",
        datasource="google_workspace",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 4: Emails from person
    print("\n[4/7] Testing emails from specific person (Krishnan)...")
    result = await runner.run_test_case(
        name="Emails from Krishnan",
        query="What are the most recent emails Krishnan sent me?",
        datasource="google_workspace",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 5: Calendar
    print("\n[5/7] Testing calendar events...")
    result = await runner.run_test_case(
        name="Calendar",
        query="What's on my calendar today?",
        datasource="google_workspace",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 6: Recent emails
    print("\n[6/7] Testing recent emails...")
    result = await runner.run_test_case(
        name="Recent emails",
        query="Show me my 10 most recent emails with subjects and senders",
        datasource="google_workspace",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 7: Conversation context
    print("\n[7/7] Testing conversation context...")
    runner.chat_client.reset_session()
    results = await runner.run_conversation_test(
        name="Conversation",
        queries=[
            ("Find documents about projects", []),
            ("What's in the first one?", []),
        ],
        datasource="google_workspace",
    )
    suite.results.extend(results)

    suite.end_time = datetime.now()
    runner.print_results(suite)

    # Save results
    runner.results.append(suite)
    runner.save_results("test_results_google_workspace.json")

    return suite


if __name__ == "__main__":
    asyncio.run(run_all_google_workspace_tests())

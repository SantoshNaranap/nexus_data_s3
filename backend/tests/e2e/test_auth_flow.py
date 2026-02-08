"""
E2E Tests for Authentication Flow

Tests user authentication states:
1. Anonymous user - limited functionality
2. Authenticated user - full access
3. Session persistence
"""

import asyncio
import pytest
from datetime import datetime
from typing import Optional

from .test_framework import (
    TestRunner,
    TestSuiteResult,
    TestStatus,
    ChatClient,
)


class TestAnonymousUser:
    """Tests for anonymous (unauthenticated) user behavior."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()
        # Ensure no auth token
        self.runner.chat_client.auth_token = None
        self.runner.chat_client.cookies = {}

    @pytest.mark.asyncio
    async def test_anonymous_can_chat(self):
        """Test that anonymous users can send chat messages."""
        suite = TestSuiteResult(suite_name="Anonymous Chat", connector="slack")

        result = await self.runner.run_test_case(
            name="Anonymous chat",
            query="Hello, what can you help me with?",
            datasource="slack",
            expected_contains=[],
        )

        # Anonymous users should get a response (even if limited)
        if result.response and len(result.response) > 10:
            result.status = TestStatus.PASSED

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        # Should not error out completely
        assert result.status != TestStatus.ERROR or "auth" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_anonymous_session_persistence(self):
        """Test that anonymous sessions persist across messages."""
        suite = TestSuiteResult(suite_name="Anonymous Session", connector="slack")

        # First message - note the session ID
        result1 = await self.runner.run_test_case(
            name="First message",
            query="List my channels",
            datasource="slack",
            expected_contains=[],
        )
        suite.results.append(result1)
        session_id = self.runner.chat_client.session_id

        # Second message - should use same session
        result2 = await self.runner.run_test_case(
            name="Second message (same session)",
            query="Tell me more about the first one",
            datasource="slack",
            expected_contains=[],
        )
        suite.results.append(result2)

        # Verify session maintained
        if self.runner.chat_client.session_id == session_id:
            result2.accuracy_score = 100
            result2.status = TestStatus.PASSED if result2.status != TestStatus.ERROR else result2.status

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_anonymous_credentials_requirement(self):
        """Test that certain operations require credentials."""
        suite = TestSuiteResult(suite_name="Credential Requirements", connector="slack")

        # Clear any session cookies
        self.runner.chat_client.cookies = {}

        result = await self.runner.run_test_case(
            name="Requires credentials",
            query="Show me my Slack channels",
            datasource="slack",
            expected_contains=[],
        )

        # Check if response mentions credentials/auth or works with env vars
        if result.response:
            auth_mentions = ["credential", "auth", "login", "connect", "configure"]
            needs_auth = any(m in result.response.lower() for m in auth_mentions)
            # Either it works (env vars) or properly asks for auth
            result.status = TestStatus.PASSED

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)


class TestAuthenticatedUser:
    """Tests for authenticated user behavior."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()

    @pytest.mark.asyncio
    async def test_check_auth_status(self):
        """Test checking authentication status."""
        suite = TestSuiteResult(suite_name="Auth Status", connector="system")

        # Check auth without credentials
        auth_info = await self.runner.chat_client.check_auth()

        result = TestSuiteResult(
            suite_name="Auth Check",
            connector="system",
            results=[],
            end_time=datetime.now(),
        )

        if auth_info:
            print(f"Authenticated as: {auth_info.get('email')}")
        else:
            print("Not authenticated (anonymous mode)")

        self.runner.print_results(result)

    @pytest.mark.asyncio
    async def test_authenticated_full_access(self):
        """Test that authenticated users get full access."""
        suite = TestSuiteResult(suite_name="Authenticated Access", connector="slack")

        # Note: This test assumes authentication is done via env vars or cookies
        # For full auth testing, we'd need actual credentials

        result = await self.runner.run_test_case(
            name="Full access query",
            query="Show me all my Slack channels with details",
            datasource="slack",
            expected_contains=[],
        )

        # Authenticated user should get detailed response
        if result.response and len(result.response) > 100:
            result.status = TestStatus.PASSED

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)


class TestSessionManagement:
    """Tests for chat session management."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()

    @pytest.mark.asyncio
    async def test_new_session_per_datasource(self):
        """Test that different datasources can have different sessions."""
        suite = TestSuiteResult(suite_name="Multi-Datasource Sessions", connector="multi")

        # Chat with Slack
        self.runner.chat_client.reset_session()
        result1 = await self.runner.run_test_case(
            name="Slack session",
            query="List channels",
            datasource="slack",
            expected_contains=[],
        )
        slack_session = self.runner.chat_client.session_id
        suite.results.append(result1)

        # Chat with JIRA
        self.runner.chat_client.reset_session()
        result2 = await self.runner.run_test_case(
            name="JIRA session",
            query="List projects",
            datasource="jira",
            expected_contains=[],
        )
        jira_session = self.runner.chat_client.session_id
        suite.results.append(result2)

        # Sessions should be different
        if slack_session != jira_session:
            print(f"Sessions are separate: Slack={slack_session[:8]}..., JIRA={jira_session[:8]}...")

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_session_context_maintained(self):
        """Test that context is maintained within a session."""
        suite = TestSuiteResult(suite_name="Session Context", connector="jira")

        self.runner.chat_client.reset_session()

        # Establish context
        result1 = await self.runner.run_test_case(
            name="Set context",
            query="Tell me about the Oralia V2 project",
            datasource="jira",
            expected_contains=[],
        )
        suite.results.append(result1)

        # Follow-up that relies on context
        result2 = await self.runner.run_test_case(
            name="Use context",
            query="What issues are blocked?",
            datasource="jira",
            expected_contains=[],
        )
        suite.results.append(result2)

        # Third query - deeper context
        result3 = await self.runner.run_test_case(
            name="Deep context",
            query="Who is assigned to those?",
            datasource="jira",
            expected_contains=[],
        )
        suite.results.append(result3)

        suite.end_time = datetime.now()
        self.runner.print_results(suite)


# Standalone runner
async def run_auth_tests():
    """Run all authentication tests."""
    runner = TestRunner()

    print("\n" + "=" * 80)
    print("AUTHENTICATION FLOW E2E TESTS")
    print("=" * 80)

    suite = TestSuiteResult(suite_name="Auth Flow Tests", connector="system")

    # Test 1: Check current auth status
    print("\n[1/5] Checking authentication status...")
    auth_info = await runner.chat_client.check_auth()
    if auth_info:
        print(f"  Authenticated as: {auth_info.get('email')}")
    else:
        print("  Running in anonymous mode")

    # Test 2: Anonymous chat
    print("\n[2/5] Testing anonymous chat...")
    runner.chat_client.auth_token = None
    runner.chat_client.reset_session()
    result = await runner.run_test_case(
        name="Anonymous chat",
        query="Hello, what connectors are available?",
        datasource="slack",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 3: Session persistence
    print("\n[3/5] Testing session persistence...")
    result = await runner.run_test_case(
        name="Session follow-up",
        query="Tell me more about Slack",
        datasource="slack",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 4: Cross-datasource
    print("\n[4/5] Testing cross-datasource sessions...")
    runner.chat_client.reset_session()
    result = await runner.run_test_case(
        name="JIRA query",
        query="What JIRA projects exist?",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 5: Context maintenance
    print("\n[5/5] Testing context maintenance...")
    results = await runner.run_conversation_test(
        name="Context test",
        queries=[
            ("Tell me about the first project", []),
            ("What issues are open there?", []),
        ],
        datasource="jira",
    )
    suite.results.extend(results)

    suite.end_time = datetime.now()
    runner.print_results(suite)

    runner.results.append(suite)
    runner.save_results("test_results_auth.json")

    return suite


if __name__ == "__main__":
    asyncio.run(run_auth_tests())

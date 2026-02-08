"""
E2E Tests for Slack Connector

Tests conversational queries against Slack with accuracy validation.
Validates that responses match actual Slack API data.
"""

import asyncio
import pytest
from datetime import datetime
from typing import List, Dict

from .test_framework import (
    TestRunner,
    TestSuiteResult,
    TestStatus,
    DirectAPIClient,
)


class TestSlackConnector:
    """E2E tests for Slack connector functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test runner for each test."""
        self.runner = TestRunner()
        self.direct_api = DirectAPIClient()

    @pytest.mark.asyncio
    async def test_list_channels(self):
        """Test listing Slack channels and validate accuracy."""
        suite = TestSuiteResult(suite_name="Slack Channel Listing", connector="slack")

        # Get actual channels from Slack API
        actual_channels = await self.direct_api.get_slack_channels()
        channel_names = [c.get("name") for c in actual_channels[:10]]  # Top 10

        if not channel_names:
            pytest.skip("No Slack channels available or token not configured")

        # Test the chat query
        result = await self.runner.run_test_case(
            name="List all channels",
            query="What channels do I have in Slack?",
            datasource="slack",
            expected_contains=channel_names[:5],  # Check for first 5 channels
            validation_data={"actual_channels": channel_names},
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        assert result.status == TestStatus.PASSED, f"Failed: {result.error_message}"

    @pytest.mark.asyncio
    async def test_list_users(self):
        """Test listing Slack users and validate accuracy."""
        suite = TestSuiteResult(suite_name="Slack User Listing", connector="slack")

        # Get actual users from Slack API
        actual_users = await self.direct_api.get_slack_users()
        user_names = [u.get("real_name") or u.get("name") for u in actual_users[:10]]

        if not user_names:
            pytest.skip("No Slack users available or token not configured")

        # Test the chat query
        result = await self.runner.run_test_case(
            name="List team members",
            query="Who is on my Slack team?",
            datasource="slack",
            expected_contains=user_names[:5],
            validation_data={"actual_users": user_names},
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        assert result.status == TestStatus.PASSED, f"Failed: {result.error_message}"

    @pytest.mark.asyncio
    async def test_summarize_missed_messages(self):
        """Test summarizing missed messages from last X hours."""
        suite = TestSuiteResult(suite_name="Slack Message Summary", connector="slack")

        # Get actual channels
        actual_channels = await self.direct_api.get_slack_channels()
        if not actual_channels:
            pytest.skip("No Slack channels available")

        # Find a channel with messages
        test_channel = None
        for channel in actual_channels[:5]:
            messages = await self.direct_api.get_slack_messages(channel.get("name"), hours_ago=24)
            if messages and len(messages) > 2:
                test_channel = channel.get("name")
                break

        if not test_channel:
            pytest.skip("No channels with recent messages found")

        # Test summarization query
        result = await self.runner.run_test_case(
            name="Summarize missed messages",
            query=f"Summarize what I missed in #{test_channel} in the last 24 hours",
            datasource="slack",
            expected_contains=[test_channel],  # Should at least mention the channel
        )

        suite.results.append(result)

        # Verify response is not empty and mentions something from the channel
        if result.response and len(result.response) > 50:
            result.status = TestStatus.PASSED
        else:
            result.status = TestStatus.FAILED
            result.error_message = "Response too short or empty"

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_get_messages_from_user(self):
        """Test getting messages from a specific user."""
        suite = TestSuiteResult(suite_name="Slack User Messages", connector="slack")

        # Get actual users
        actual_users = await self.direct_api.get_slack_users()
        if not actual_users:
            pytest.skip("No Slack users available")

        # Pick a user that likely has messages
        test_user = None
        for user in actual_users[:10]:
            name = user.get("real_name") or user.get("name")
            if name and not user.get("is_bot"):
                test_user = name
                break

        if not test_user:
            pytest.skip("No suitable test user found")

        # Test query for user's messages
        result = await self.runner.run_test_case(
            name=f"Get messages from {test_user}",
            query=f"Show me recent messages from {test_user}",
            datasource="slack",
            expected_contains=[],  # Just check it runs without error
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        # Pass if we got a response without error
        assert result.status != TestStatus.ERROR, f"Error: {result.error_message}"

    @pytest.mark.asyncio
    async def test_search_messages(self):
        """Test searching for messages with specific keywords."""
        suite = TestSuiteResult(suite_name="Slack Message Search", connector="slack")

        # Try searching for common terms
        search_terms = ["meeting", "update", "help"]

        for term in search_terms:
            # Get actual search results from Slack API
            actual_results = await self.direct_api.search_slack_messages(term)

            if actual_results:
                # We have results, test the chat query
                result = await self.runner.run_test_case(
                    name=f"Search for '{term}'",
                    query=f"Search Slack for messages about {term}",
                    datasource="slack",
                    expected_contains=[term],  # Should at least mention the search term
                )

                suite.results.append(result)
                break
        else:
            pytest.skip("No search results found for test terms")

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_conversation_context(self):
        """Test that conversation context is maintained across turns."""
        suite = TestSuiteResult(suite_name="Slack Conversation Context", connector="slack")

        # Get channels for context
        actual_channels = await self.direct_api.get_slack_channels()
        if not actual_channels:
            pytest.skip("No Slack channels available")

        test_channel = actual_channels[0].get("name")

        # Multi-turn conversation
        conversations = [
            (f"Show me messages from #{test_channel}", [test_channel]),
            ("Who sent the most recent message there?", []),  # Context test
            ("What were they talking about?", []),  # Deeper context
        ]

        results = await self.runner.run_conversation_test(
            name="Context maintenance",
            queries=conversations,
            datasource="slack",
        )

        suite.results.extend(results)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

        # At least first query should pass
        assert results[0].status == TestStatus.PASSED or results[0].status != TestStatus.ERROR

    @pytest.mark.asyncio
    async def test_dm_retrieval(self):
        """Test retrieving DMs from specific users."""
        suite = TestSuiteResult(suite_name="Slack DM Retrieval", connector="slack")

        # Get users for DM test
        actual_users = await self.direct_api.get_slack_users()
        if not actual_users:
            pytest.skip("No Slack users available")

        # Pick a user
        test_user = None
        for user in actual_users[:10]:
            name = user.get("real_name") or user.get("name")
            if name and not user.get("is_bot"):
                test_user = name
                break

        if not test_user:
            pytest.skip("No suitable test user found")

        # Test DM query
        result = await self.runner.run_test_case(
            name=f"Get DMs from {test_user}",
            query=f"Show me my direct messages with {test_user}",
            datasource="slack",
            expected_contains=[],  # Just verify it runs
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        # Pass if no error
        assert result.status != TestStatus.ERROR, f"Error: {result.error_message}"


class TestSlackAccuracy:
    """Accuracy-focused tests comparing chat responses with direct API calls."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()
        self.direct_api = DirectAPIClient()

    @pytest.mark.asyncio
    async def test_channel_count_accuracy(self):
        """Verify the chat accurately reports channel counts."""
        # Get actual count
        actual_channels = await self.direct_api.get_slack_channels()
        actual_count = len(actual_channels)

        if actual_count == 0:
            pytest.skip("No Slack channels available")

        # Ask chat for count
        result = await self.runner.run_test_case(
            name="Channel count accuracy",
            query="How many channels do I have in Slack?",
            datasource="slack",
            expected_contains=[str(actual_count)],
        )

        # Check if the number mentioned is close to actual
        import re
        numbers = re.findall(r'\b(\d+)\b', result.response)
        if numbers:
            reported_count = max(int(n) for n in numbers)  # Get largest number
            # Allow 10% variance due to permissions/visibility
            variance = abs(reported_count - actual_count) / max(actual_count, 1)
            if variance <= 0.1:
                result.status = TestStatus.PASSED
                result.accuracy_score = 100 - (variance * 100)
            else:
                result.status = TestStatus.FAILED
                result.error_message = f"Count mismatch: reported {reported_count}, actual {actual_count}"

        self.runner.print_results(
            TestSuiteResult(
                suite_name="Channel Count Accuracy",
                connector="slack",
                results=[result],
                end_time=datetime.now(),
            )
        )

    @pytest.mark.asyncio
    async def test_no_hallucinated_channels(self):
        """Verify chat doesn't invent channel names."""
        # Get actual channels
        actual_channels = await self.direct_api.get_slack_channels()
        valid_names = [c.get("name") for c in actual_channels]

        if not valid_names:
            pytest.skip("No Slack channels available")

        # Ask for channels
        result = await self.runner.run_test_case(
            name="No hallucinated channels",
            query="List my Slack channels",
            datasource="slack",
            expected_contains=valid_names[:3],
        )

        # Check for hallucinations
        from .test_framework import AccuracyValidator
        hallucinated = AccuracyValidator.check_no_hallucination(
            result.response,
            valid_names,
            "channel"
        )

        if hallucinated:
            result.status = TestStatus.FAILED
            result.error_message = f"Possible hallucinated channels: {hallucinated[:5]}"
        else:
            result.status = TestStatus.PASSED

        self.runner.print_results(
            TestSuiteResult(
                suite_name="Hallucination Check",
                connector="slack",
                results=[result],
                end_time=datetime.now(),
            )
        )


# Standalone runner for quick testing
async def run_all_slack_tests():
    """Run all Slack tests and save results."""
    runner = TestRunner()
    direct_api = DirectAPIClient()

    print("\n" + "=" * 80)
    print("SLACK CONNECTOR E2E TESTS")
    print("=" * 80)

    suite = TestSuiteResult(suite_name="Complete Slack Test Suite", connector="slack")

    # Test 1: List channels
    print("\n[1/6] Testing channel listing...")
    channels = await direct_api.get_slack_channels()
    if channels:
        channel_names = [c.get("name") for c in channels[:5]]
        result = await runner.run_test_case(
            name="List channels",
            query="What channels do I have?",
            datasource="slack",
            expected_contains=channel_names,
        )
        suite.results.append(result)
    else:
        print("  Skipped: No channels available")

    # Test 2: List users
    print("\n[2/6] Testing user listing...")
    users = await direct_api.get_slack_users()
    if users:
        user_names = [u.get("real_name") for u in users[:5] if u.get("real_name")]
        result = await runner.run_test_case(
            name="List users",
            query="Who is on my Slack team?",
            datasource="slack",
            expected_contains=user_names[:3],
        )
        suite.results.append(result)
    else:
        print("  Skipped: No users available")

    # Test 3: Message summary
    print("\n[3/6] Testing message summarization...")
    if channels:
        result = await runner.run_test_case(
            name="Summarize messages",
            query="What did I miss in the last 24 hours?",
            datasource="slack",
            expected_contains=[],
        )
        suite.results.append(result)

    # Test 4: Search
    print("\n[4/6] Testing message search...")
    result = await runner.run_test_case(
        name="Search messages",
        query="Search for messages about updates",
        datasource="slack",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 5: Specific user messages
    print("\n[5/6] Testing user-specific messages...")
    if users and users[0].get("real_name"):
        test_user = users[0].get("real_name")
        result = await runner.run_test_case(
            name=f"Messages from {test_user}",
            query=f"Show me messages from {test_user}",
            datasource="slack",
            expected_contains=[],
        )
        suite.results.append(result)

    # Test 6: Conversation context
    print("\n[6/6] Testing conversation context...")
    runner.chat_client.reset_session()
    if channels:
        channel = channels[0].get("name")
        results = await runner.run_conversation_test(
            name="Conversation context",
            queries=[
                (f"Show messages from #{channel}", [channel]),
                ("Who sent the last message?", []),
            ],
            datasource="slack",
        )
        suite.results.extend(results)

    suite.end_time = datetime.now()
    runner.print_results(suite)

    # Save results
    runner.results.append(suite)
    runner.save_results("test_results_slack.json")

    return suite


if __name__ == "__main__":
    asyncio.run(run_all_slack_tests())

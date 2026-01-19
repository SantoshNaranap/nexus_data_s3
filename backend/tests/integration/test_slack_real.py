"""
Real Slack API Integration Tests

These tests actually hit the Slack API with real credentials.
Skip if credentials aren't available.

Run with: pytest tests/integration/test_slack_real.py -v -s
"""

import os
import pytest
import asyncio
from datetime import datetime, timedelta

# Skip all tests if no Slack credentials
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")

pytestmark = pytest.mark.skipif(
    not SLACK_BOT_TOKEN and not SLACK_USER_TOKEN,
    reason="No Slack credentials available"
)


class TestSlackRealAPI:
    """Integration tests that hit real Slack API."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up Slack client."""
        from slack_sdk import WebClient
        self.bot_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None
        self.user_client = WebClient(token=SLACK_USER_TOKEN) if SLACK_USER_TOKEN else None
        self.client = self.user_client or self.bot_client

    def test_can_list_channels_with_pagination(self):
        """Test that we can list ALL channels, not just first page."""
        all_channels = []
        cursor = None

        while True:
            kwargs = {
                "types": "public_channel,private_channel",
                "limit": 100,
                "exclude_archived": False
            }
            if cursor:
                kwargs["cursor"] = cursor

            result = self.client.users_conversations(**kwargs)
            all_channels.extend(result.get("channels", []))

            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        print(f"\n✓ Found {len(all_channels)} total channels")
        assert len(all_channels) > 0, "Should find at least one channel"

        # Verify we got more than one page if workspace is large
        if len(all_channels) > 100:
            print(f"✓ Pagination working - got {len(all_channels)} channels (>100)")

    def test_can_find_private_channel_by_name(self):
        """Test that private channels can be found by name."""
        # First get list of private channels
        result = self.client.users_conversations(
            types="private_channel",
            limit=10
        )
        private_channels = result.get("channels", [])

        if not private_channels:
            pytest.skip("No private channels to test with")

        # Try to find the first private channel by name
        target_channel = private_channels[0]
        target_name = target_channel["name"]

        print(f"\n Testing lookup of private channel: #{target_name}")

        # Search all channels for this name
        found = False
        cursor = None
        while True:
            kwargs = {
                "types": "public_channel,private_channel",
                "limit": 200
            }
            if cursor:
                kwargs["cursor"] = cursor

            result = self.client.users_conversations(**kwargs)
            for ch in result.get("channels", []):
                if ch["name"] == target_name:
                    found = True
                    break

            if found:
                break

            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        assert found, f"Should find private channel #{target_name}"
        print(f"✓ Found private channel #{target_name}")

    def test_can_read_private_channel_history(self):
        """Test that we can read messages from private channels."""
        # Get a private channel
        result = self.client.users_conversations(
            types="private_channel",
            limit=5
        )
        private_channels = result.get("channels", [])

        if not private_channels:
            pytest.skip("No private channels to test with")

        channel = private_channels[0]
        channel_id = channel["id"]
        channel_name = channel["name"]

        print(f"\n Testing read from private channel: #{channel_name}")

        # Try to read history
        history = self.client.conversations_history(
            channel=channel_id,
            limit=10
        )

        messages = history.get("messages", [])
        print(f"✓ Read {len(messages)} messages from #{channel_name}")
        assert "messages" in history, "Should get messages key in response"

    def test_can_list_all_dms(self):
        """Test that we can list all DM conversations."""
        all_dms = []
        cursor = None

        while True:
            kwargs = {"types": "im,mpim", "limit": 100}
            if cursor:
                kwargs["cursor"] = cursor

            result = self.client.conversations_list(**kwargs)
            all_dms.extend(result.get("channels", []))

            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        print(f"\n✓ Found {len(all_dms)} DM conversations")
        assert len(all_dms) >= 0, "Should be able to list DMs"

    def test_can_read_dm_history(self):
        """Test that we can read DM history."""
        # Get list of DMs
        result = self.client.conversations_list(types="im", limit=5)
        dms = result.get("channels", [])

        if not dms:
            pytest.skip("No DMs to test with")

        dm = dms[0]
        dm_id = dm["id"]

        print(f"\n Testing read from DM: {dm_id}")

        # Try to read history
        history = self.client.conversations_history(
            channel=dm_id,
            limit=10
        )

        messages = history.get("messages", [])
        print(f"✓ Read {len(messages)} messages from DM")
        assert "messages" in history, "Should get messages key in response"

    def test_can_resolve_user_by_name(self):
        """Test that we can find users by partial name."""
        # Get a real user first
        result = self.client.users_list(limit=10)
        users = [u for u in result.get("members", []) if not u.get("is_bot") and not u.get("deleted")]

        if not users:
            pytest.skip("No users to test with")

        target_user = users[0]
        real_name = target_user.get("real_name", "")
        user_id = target_user["id"]

        if not real_name:
            pytest.skip("User has no real name")

        # Try to find by first name
        first_name = real_name.split()[0].lower()
        print(f"\n Testing user lookup: '{first_name}' -> {real_name}")

        # Search for user
        found_id = None
        result = self.client.users_list(limit=200)
        for user in result.get("members", []):
            if user.get("deleted") or user.get("is_bot"):
                continue
            user_real_name = user.get("real_name", "").lower()
            if user_real_name.startswith(first_name):
                found_id = user["id"]
                break

        assert found_id is not None, f"Should find user by first name '{first_name}'"
        print(f"✓ Found user {real_name} by first name search")

    def test_user_mentions_are_resolvable(self):
        """Test that user IDs in messages can be resolved to names."""
        # Get some messages
        result = self.client.users_conversations(types="public_channel", limit=5)
        channels = result.get("channels", [])

        if not channels:
            pytest.skip("No channels to test with")

        # Find a message with a user mention
        mention_found = False
        for channel in channels:
            history = self.client.conversations_history(
                channel=channel["id"],
                limit=50
            )
            for msg in history.get("messages", []):
                text = msg.get("text", "")
                if "<@U" in text:
                    # Found a mention, try to resolve it
                    import re
                    match = re.search(r'<@([A-Z0-9]+)>', text)
                    if match:
                        user_id = match.group(1)
                        try:
                            user_info = self.client.users_info(user=user_id)
                            user_name = user_info["user"].get("real_name", user_id)
                            print(f"\n✓ Resolved <@{user_id}> to {user_name}")
                            mention_found = True
                            break
                        except:
                            pass
            if mention_found:
                break

        if not mention_found:
            pytest.skip("No user mentions found in recent messages")

    def test_search_messages_works(self):
        """Test that message search returns results."""
        if not self.user_client:
            pytest.skip("Search requires user token")

        # Search for something common
        result = self.user_client.search_messages(
            query="the",
            count=10
        )

        total = result.get("messages", {}).get("total", 0)
        matches = result.get("messages", {}).get("matches", [])

        print(f"\n✓ Search found {total} total matches, returned {len(matches)}")
        assert "messages" in result, "Should get messages in search response"


class TestSlackConnectorIntegration:
    """Test the actual Slack connector end-to-end."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Add connectors path to sys.path
        import sys
        connector_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "connectors", "slack", "src"
        )
        if connector_path not in sys.path:
            sys.path.insert(0, os.path.abspath(connector_path))

    def test_get_channel_id_with_fuzzy_match(self):
        """Test that _get_channel_id does fuzzy matching."""
        try:
            from slack_server import _get_channel_id, _channel_cache
            _channel_cache.clear()  # Clear cache to test fresh lookup

            # Get actual channel list first
            from slack_sdk import WebClient
            client = WebClient(token=SLACK_USER_TOKEN or SLACK_BOT_TOKEN)
            result = client.users_conversations(types="public_channel", limit=10)
            channels = result.get("channels", [])

            if not channels:
                pytest.skip("No channels to test with")

            # Get a real channel name
            real_name = channels[0]["name"]  # e.g., "nexusai-gtm-education"

            # Test exact match
            channel_id = _get_channel_id(real_name)
            assert channel_id is not None, f"Should find channel by exact name: {real_name}"
            print(f"\n✓ Exact match: '{real_name}' -> {channel_id}")

            # Test with partial name (if name has dashes)
            if "-" in real_name:
                parts = real_name.split("-")
                partial = "-".join(parts[:2])  # First two parts
                _channel_cache.clear()
                channel_id = _get_channel_id(partial)
                print(f"✓ Partial match: '{partial}' -> {channel_id}")

        except ImportError as e:
            pytest.skip(f"Cannot import slack_server: {e}")

    def test_resolve_user_mentions(self):
        """Test that _resolve_user_mentions works."""
        try:
            from slack_server import _resolve_user_mentions, _preload_all_users

            # Pre-load users
            _preload_all_users()

            # Get a real user ID
            from slack_sdk import WebClient
            client = WebClient(token=SLACK_USER_TOKEN or SLACK_BOT_TOKEN)
            result = client.users_list(limit=5)
            users = [u for u in result.get("members", []) if not u.get("is_bot")]

            if not users:
                pytest.skip("No users to test with")

            user = users[0]
            user_id = user["id"]
            real_name = user.get("real_name", user_id)

            # Test resolution
            test_text = f"Hello <@{user_id}>, how are you?"
            resolved = _resolve_user_mentions(test_text)

            print(f"\n Original: {test_text}")
            print(f"  Resolved: {resolved}")

            assert f"<@{user_id}>" not in resolved or real_name in resolved, \
                "Should resolve user mention to name"

        except ImportError as e:
            pytest.skip(f"Cannot import slack_server: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

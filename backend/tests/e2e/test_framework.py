"""
E2E Test Framework - Conversational Testing with Accuracy Validation

This framework enables end-to-end testing of the chat interface by:
1. Sending real messages to the API
2. Validating responses against direct API calls
3. Testing various user states (anonymous, authenticated)
4. Testing conversation context maintenance
"""

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import httpx
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    PENDING = "pending"


@dataclass
class TestResult:
    """Result of a single test case."""
    name: str
    query: str
    response: str = ""
    status: TestStatus = field(default=TestStatus.PENDING)
    expected_contains: List[str] = field(default_factory=list)
    actual_matches: List[str] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)
    accuracy_score: float = 0.0
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    raw_data: Optional[Dict] = None  # Direct API response for comparison


@dataclass
class TestSuiteResult:
    """Result of a test suite run."""
    suite_name: str
    connector: str
    results: List[TestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    @property
    def passed(self) -> int:
        return len([r for r in self.results if r.status == TestStatus.PASSED])

    @property
    def failed(self) -> int:
        return len([r for r in self.results if r.status == TestStatus.FAILED])

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total > 0 else 0.0


class ChatClient:
    """Client for interacting with the chat API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
        self.auth_token: Optional[str] = None
        self.cookies: Dict[str, str] = {}

    async def send_message(
        self,
        message: str,
        datasource: str,
        session_id: Optional[str] = None,
    ) -> Tuple[str, Optional[List[Dict]]]:
        """Send a chat message and get response."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "message": message,
                "datasource": datasource,
                "session_id": session_id or self.session_id,
            }

            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            response = await client.post(
                f"{self.base_url}/api/chat/message",
                json=payload,
                headers=headers,
                cookies=self.cookies,
            )

            if response.status_code != 200:
                raise Exception(f"Chat API error: {response.status_code} - {response.text}")

            data = response.json()
            self.session_id = data.get("session_id")

            return data.get("message", ""), data.get("tool_calls")

    async def send_message_stream(
        self,
        message: str,
        datasource: str,
        session_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """Send a chat message and collect streamed response."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "message": message,
                "datasource": datasource,
                "session_id": session_id or self.session_id,
            }

            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            full_response = ""
            tool_calls = []

            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat/message/stream",
                json=payload,
                headers=headers,
                cookies=self.cookies,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") == "content":
                                full_response += data.get("content", "")
                            elif data.get("type") == "session":
                                self.session_id = data.get("session_id")
                            elif data.get("type") == "agent_step":
                                step = data.get("step", {})
                                if step.get("type") == "tool_call":
                                    tool_calls.append(step)
                        except json.JSONDecodeError:
                            pass

            return full_response, tool_calls

    async def login(self, email: str, password: str) -> bool:
        """Authenticate with the API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password},
            )

            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                # Store cookies for session
                for cookie in response.cookies:
                    self.cookies[cookie.name] = cookie.value
                return True
            return False

    async def check_auth(self) -> Optional[Dict]:
        """Check current authentication status."""
        async with httpx.AsyncClient() as client:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            response = await client.get(
                f"{self.base_url}/api/auth/me",
                headers=headers,
                cookies=self.cookies,
            )

            if response.status_code == 200:
                return response.json()
            return None

    def reset_session(self):
        """Reset chat session for fresh conversation."""
        self.session_id = None


class AccuracyValidator:
    """Validates chat responses against expected data."""

    @staticmethod
    def extract_items(response: str, pattern: str = None) -> List[str]:
        """Extract items from a response using pattern matching."""
        items = []

        # Common patterns for extracting structured data
        patterns = [
            r'\*\*([^*]+)\*\*',  # Bold markdown items
            r'- ([^\n]+)',  # Bullet points
            r'\d+\.\s+([^\n]+)',  # Numbered lists
            r'"([^"]+)"',  # Quoted items
            r'`([^`]+)`',  # Code/inline items
        ]

        if pattern:
            patterns = [pattern]

        for p in patterns:
            matches = re.findall(p, response)
            items.extend(matches)

        return list(set(items))

    @staticmethod
    def check_contains(response: str, expected_items: List[str], case_sensitive: bool = False) -> Tuple[List[str], List[str]]:
        """Check if response contains expected items."""
        found = []
        missing = []

        check_response = response if case_sensitive else response.lower()

        for item in expected_items:
            check_item = item if case_sensitive else item.lower()
            if check_item in check_response:
                found.append(item)
            else:
                missing.append(item)

        return found, missing

    @staticmethod
    def calculate_accuracy(found: List[str], expected: List[str]) -> float:
        """Calculate accuracy score as percentage of expected items found."""
        if not expected:
            return 100.0
        return (len(found) / len(expected)) * 100

    @staticmethod
    def check_no_hallucination(response: str, valid_items: List[str], item_type: str = "item") -> List[str]:
        """Check for hallucinated items not in valid list."""
        # This is a heuristic check - extract items and compare to valid list
        extracted = AccuracyValidator.extract_items(response)
        hallucinated = []

        valid_lower = [v.lower() for v in valid_items]

        for item in extracted:
            item_lower = item.lower()
            # Check if extracted item matches any valid item
            if not any(v in item_lower or item_lower in v for v in valid_lower):
                # Could be a hallucinated item
                hallucinated.append(item)

        return hallucinated


class DirectAPIClient:
    """Direct API clients for validation against actual services."""

    def __init__(self):
        self.slack_token = os.getenv("SLACK_BOT_TOKEN")
        self.slack_user_token = os.getenv("SLACK_USER_TOKEN")
        self.jira_url = os.getenv("JIRA_URL")
        self.jira_email = os.getenv("JIRA_EMAIL")
        self.jira_token = os.getenv("JIRA_API_TOKEN")

    async def get_slack_channels(self) -> List[Dict]:
        """Get Slack channels directly from API."""
        if not self.slack_token:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://slack.com/api/conversations.list",
                headers={"Authorization": f"Bearer {self.slack_token}"},
                params={"types": "public_channel,private_channel", "limit": 100},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("channels", [])
        return []

    async def get_slack_users(self) -> List[Dict]:
        """Get Slack users directly from API."""
        if not self.slack_token:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://slack.com/api/users.list",
                headers={"Authorization": f"Bearer {self.slack_token}"},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return [m for m in data.get("members", []) if not m.get("is_bot") and not m.get("deleted")]
        return []

    async def get_slack_messages(self, channel: str, hours_ago: int = 24) -> List[Dict]:
        """Get recent Slack messages from a channel."""
        if not self.slack_token:
            return []

        # First, find channel ID
        channels = await self.get_slack_channels()
        channel_id = None
        for c in channels:
            if c.get("name") == channel.replace("#", ""):
                channel_id = c.get("id")
                break

        if not channel_id:
            return []

        oldest = (datetime.now() - timedelta(hours=hours_ago)).timestamp()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://slack.com/api/conversations.history",
                headers={"Authorization": f"Bearer {self.slack_token}"},
                params={"channel": channel_id, "oldest": oldest, "limit": 100},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("messages", [])
        return []

    async def search_slack_messages(self, query: str) -> List[Dict]:
        """Search Slack messages."""
        # Note: search requires user token with search:read scope
        token = self.slack_user_token or self.slack_token
        if not token:
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://slack.com/api/search.messages",
                headers={"Authorization": f"Bearer {token}"},
                params={"query": query, "count": 20},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("messages", {}).get("matches", [])
        return []

    async def get_jira_projects(self) -> List[Dict]:
        """Get JIRA projects directly from API."""
        if not all([self.jira_url, self.jira_email, self.jira_token]):
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/project",
                auth=(self.jira_email, self.jira_token),
            )

            if response.status_code == 200:
                return response.json()
        return []

    async def search_jira_issues(self, jql: str, max_results: int = 50) -> List[Dict]:
        """Search JIRA issues with JQL."""
        if not all([self.jira_url, self.jira_email, self.jira_token]):
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/search",
                auth=(self.jira_email, self.jira_token),
                params={"jql": jql, "maxResults": max_results},
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("issues", [])
        return []

    async def get_jira_sprints(self, board_id: int) -> List[Dict]:
        """Get JIRA sprints for a board."""
        if not all([self.jira_url, self.jira_email, self.jira_token]):
            return []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/agile/1.0/board/{board_id}/sprint",
                auth=(self.jira_email, self.jira_token),
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("values", [])
        return []


class TestRunner:
    """Runs E2E tests and collects results."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.chat_client = ChatClient(base_url)
        self.direct_api = DirectAPIClient()
        self.validator = AccuracyValidator()
        self.results: List[TestSuiteResult] = []

    async def run_test_case(
        self,
        name: str,
        query: str,
        datasource: str,
        expected_contains: List[str] = None,
        validation_data: Optional[Dict] = None,
        use_stream: bool = False,
    ) -> TestResult:
        """Run a single test case."""
        import time

        start_time = time.time()
        result = TestResult(
            name=name,
            query=query,
            response="",
            expected_contains=expected_contains or [],
        )

        try:
            if use_stream:
                response, tool_calls = await self.chat_client.send_message_stream(query, datasource)
            else:
                response, tool_calls = await self.chat_client.send_message(query, datasource)

            result.response = response
            result.duration_ms = (time.time() - start_time) * 1000

            # Validate response contains expected items
            if expected_contains:
                found, missing = self.validator.check_contains(response, expected_contains)
                result.actual_matches = found
                result.missing_items = missing
                result.accuracy_score = self.validator.calculate_accuracy(found, expected_contains)
            else:
                result.accuracy_score = 100.0  # No specific validation needed

            # Store validation data if provided
            if validation_data:
                result.raw_data = validation_data

            # Determine pass/fail
            if result.accuracy_score >= 80:  # 80% threshold for passing
                result.status = TestStatus.PASSED
            else:
                result.status = TestStatus.FAILED
                result.error_message = f"Accuracy {result.accuracy_score:.1f}% below threshold. Missing: {result.missing_items}"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            result.duration_ms = (time.time() - start_time) * 1000

        return result

    async def run_conversation_test(
        self,
        name: str,
        queries: List[Tuple[str, List[str]]],  # (query, expected_contains)
        datasource: str,
    ) -> List[TestResult]:
        """Run a multi-turn conversation test."""
        results = []
        self.chat_client.reset_session()

        for i, (query, expected) in enumerate(queries):
            result = await self.run_test_case(
                name=f"{name} - Turn {i+1}",
                query=query,
                datasource=datasource,
                expected_contains=expected,
            )
            results.append(result)

            # If a turn fails badly, skip remaining turns
            if result.status == TestStatus.ERROR:
                break

        return results

    def print_results(self, suite_result: TestSuiteResult):
        """Print test results in a readable format."""
        print("\n" + "=" * 80)
        print(f"TEST SUITE: {suite_result.suite_name}")
        print(f"Connector: {suite_result.connector}")
        print(f"Results: {suite_result.passed}/{suite_result.total} passed ({suite_result.pass_rate:.1f}%)")
        print("=" * 80)

        for result in suite_result.results:
            status_icon = {
                TestStatus.PASSED: "✓",
                TestStatus.FAILED: "✗",
                TestStatus.SKIPPED: "○",
                TestStatus.ERROR: "⚠",
            }.get(result.status, "?")

            print(f"\n{status_icon} {result.name}")
            print(f"  Query: {result.query[:60]}{'...' if len(result.query) > 60 else ''}")
            print(f"  Duration: {result.duration_ms:.0f}ms")

            if result.status == TestStatus.PASSED:
                print(f"  Accuracy: {result.accuracy_score:.1f}%")
            elif result.status == TestStatus.FAILED:
                print(f"  Accuracy: {result.accuracy_score:.1f}%")
                print(f"  Missing: {result.missing_items[:3]}{'...' if len(result.missing_items) > 3 else ''}")
            elif result.status == TestStatus.ERROR:
                print(f"  Error: {result.error_message}")

        print("\n" + "=" * 80)

    def save_results(self, filepath: str):
        """Save all results to a JSON file."""
        output = []
        for suite in self.results:
            suite_data = {
                "suite_name": suite.suite_name,
                "connector": suite.connector,
                "passed": suite.passed,
                "failed": suite.failed,
                "total": suite.total,
                "pass_rate": suite.pass_rate,
                "start_time": suite.start_time.isoformat(),
                "end_time": suite.end_time.isoformat() if suite.end_time else None,
                "results": [
                    {
                        "name": r.name,
                        "status": r.status.value,
                        "query": r.query,
                        "response": r.response[:500],  # Truncate for file size
                        "accuracy_score": r.accuracy_score,
                        "missing_items": r.missing_items,
                        "error_message": r.error_message,
                        "duration_ms": r.duration_ms,
                    }
                    for r in suite.results
                ],
            }
            output.append(suite_data)

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Results saved to {filepath}")


# Export main classes
__all__ = [
    "ChatClient",
    "AccuracyValidator",
    "DirectAPIClient",
    "TestRunner",
    "TestResult",
    "TestSuiteResult",
    "TestStatus",
]

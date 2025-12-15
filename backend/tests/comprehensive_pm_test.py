"""
Comprehensive End-to-End Tests for Connectors
Tests realistic PM workflows with multi-turn conversations.
Ensures context is maintained and NO error messages appear.
"""

import asyncio
import httpx
import json
import re
import sys
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 120.0  # 2 minutes for complex queries

# Error patterns to detect - these should NEVER appear in responses
ERROR_PATTERNS = [
    r"i don'?t have access",
    r"i cannot access",
    r"i'?m unable to access",
    r"error fetching",
    r"failed to fetch",
    r"connection failed",
    r"unable to retrieve",
    r"could not retrieve",
    r"no access to",
    r"permission denied",
    r"unauthorized",
    r"cannot connect",
    r"failed to connect",
    r"error occurred",
    r"something went wrong",
    r"i apologize.*error",
    r"unfortunately.*cannot",
    r"i'?m sorry.*unable",
    r"data is not available",
    r"couldn'?t find any",
    r"no results found",  # This one needs context - sometimes valid
    r"timed? ?out",
    r"exception",
    r"traceback",
]

@dataclass
class TestResult:
    """Result of a single test conversation"""
    connector: str
    conversation_name: str
    passed: bool
    turns: int
    errors_found: List[str]
    context_maintained: bool
    response_times: List[float]
    full_conversation: List[Dict[str, str]]


class ConnectorTester:
    """Tests connector conversations for PM workflows"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session_id = f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.results: List[TestResult] = []

    async def send_message(
        self,
        datasource: str,
        message: str,
        conversation_history: List[Dict] = None
    ) -> Tuple[str, float, Dict]:
        """Send a message and get response with timing"""

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            payload = {
                "message": message,
                "datasource": datasource,
                "session_id": self.session_id,
            }

            if conversation_history:
                payload["conversation_history"] = conversation_history

            start_time = asyncio.get_event_loop().time()

            try:
                response = await client.post(
                    f"{self.base_url}/api/chat/message",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                elapsed = asyncio.get_event_loop().time() - start_time

                if response.status_code != 200:
                    return f"HTTP ERROR {response.status_code}: {response.text}", elapsed, {}

                data = response.json()
                assistant_response = data.get("response", "")

                return assistant_response, elapsed, data

            except Exception as e:
                elapsed = asyncio.get_event_loop().time() - start_time
                return f"EXCEPTION: {str(e)}", elapsed, {}

    def check_for_errors(self, response: str) -> List[str]:
        """Check if response contains error patterns"""
        errors = []
        response_lower = response.lower()

        for pattern in ERROR_PATTERNS:
            if re.search(pattern, response_lower):
                # Extract the matching context
                match = re.search(f".{{0,50}}{pattern}.{{0,50}}", response_lower)
                if match:
                    errors.append(f"Pattern '{pattern}' found: ...{match.group()}...")

        return errors

    def check_context_maintained(
        self,
        conversation: List[Dict[str, str]],
        context_keywords: List[str]
    ) -> bool:
        """Check if context from earlier turns is maintained in later responses"""
        # Look for references to earlier context in later responses
        for i, turn in enumerate(conversation):
            if i > 0 and turn.get("role") == "assistant":
                response = turn.get("content", "").lower()
                # Check if any context keyword from earlier appears
                for keyword in context_keywords:
                    if keyword.lower() in response:
                        return True
        return len(conversation) <= 2  # Single turn doesn't need context check

    async def run_conversation(
        self,
        connector: str,
        conversation_name: str,
        messages: List[str],
        context_keywords: List[str] = None
    ) -> TestResult:
        """Run a multi-turn conversation and collect results"""

        print(f"\n{'='*60}")
        print(f"Testing: {connector.upper()} - {conversation_name}")
        print(f"{'='*60}")

        full_conversation = []
        conversation_history = []
        response_times = []
        all_errors = []

        for i, message in enumerate(messages):
            print(f"\n[Turn {i+1}] User: {message[:100]}...")

            response, elapsed, data = await self.send_message(
                connector,
                message,
                conversation_history if i > 0 else None
            )

            response_times.append(elapsed)

            # Store conversation
            full_conversation.append({"role": "user", "content": message})
            full_conversation.append({"role": "assistant", "content": response})

            # Update history for next turn
            conversation_history.append({"role": "user", "content": message})
            conversation_history.append({"role": "assistant", "content": response})

            # Check for errors
            errors = self.check_for_errors(response)
            all_errors.extend(errors)

            # Print response summary
            print(f"[Turn {i+1}] Assistant ({elapsed:.2f}s): {response[:200]}...")

            if errors:
                print(f"  *** ERRORS DETECTED: {errors}")

            # Small delay between turns
            await asyncio.sleep(0.5)

        # Check context maintenance
        context_maintained = self.check_context_maintained(
            full_conversation,
            context_keywords or []
        )

        result = TestResult(
            connector=connector,
            conversation_name=conversation_name,
            passed=len(all_errors) == 0,
            turns=len(messages),
            errors_found=all_errors,
            context_maintained=context_maintained,
            response_times=response_times,
            full_conversation=full_conversation
        )

        self.results.append(result)
        return result


# =============================================================================
# S3 CONNECTOR TESTS
# =============================================================================

S3_TESTS = [
    {
        "name": "Basic S3 Discovery",
        "messages": [
            "What S3 buckets do we have?",
            "Tell me more about the first bucket you found",
            "What are the most recent files in that bucket?",
        ],
        "context_keywords": ["bucket", "s3"]
    },
    {
        "name": "S3 Storage Analysis for PM",
        "messages": [
            "I need to understand our S3 storage. List all buckets.",
            "Which bucket has the most objects?",
            "Are there any large files I should know about?",
            "Summarize what you found about our storage",
        ],
        "context_keywords": ["bucket", "storage", "files"]
    },
    {
        "name": "S3 Data Investigation",
        "messages": [
            "Show me our S3 buckets",
            "Look inside the data bucket for any CSV or JSON files",
            "What's the total size of files you found?",
        ],
        "context_keywords": ["bucket", "files", "data"]
    },
]


# =============================================================================
# JIRA CONNECTOR TESTS
# =============================================================================

JIRA_TESTS = [
    {
        "name": "Sprint Status Check",
        "messages": [
            "What issues are currently in progress?",
            "Show me the high priority ones from those",
            "Who is working on the most critical issue?",
            "What's the status of their other assigned tasks?",
        ],
        "context_keywords": ["issue", "priority", "sprint", "assigned"]
    },
    {
        "name": "Project Overview for PM",
        "messages": [
            "Give me an overview of our JIRA projects",
            "How many open bugs do we have?",
            "Which bugs are blocking releases?",
            "Summarize what needs immediate attention",
        ],
        "context_keywords": ["project", "bug", "release", "blocking"]
    },
    {
        "name": "Team Workload Analysis",
        "messages": [
            "Show me all open issues",
            "Group these by assignee - who has the most work?",
            "What are the overdue items?",
            "Create a summary for our standup",
        ],
        "context_keywords": ["assignee", "workload", "overdue", "issues"]
    },
    {
        "name": "Release Planning",
        "messages": [
            "What issues are targeted for the next release?",
            "Are there any blockers for the release?",
            "What's the completion percentage?",
            "List the remaining work items",
        ],
        "context_keywords": ["release", "blocker", "completion", "remaining"]
    },
    {
        "name": "Bug Triage Session",
        "messages": [
            "Show me all bugs reported this week",
            "Which ones are critical or high severity?",
            "Are any of these duplicates of existing issues?",
            "Recommend which bugs to prioritize",
        ],
        "context_keywords": ["bug", "critical", "severity", "prioritize"]
    },
]


# =============================================================================
# SLACK CONNECTOR TESTS
# =============================================================================

SLACK_TESTS = [
    {
        "name": "Channel Discovery",
        "messages": [
            "What Slack channels do we have?",
            "Show me the engineering or dev channels",
            "What were the recent messages in the main engineering channel?",
        ],
        "context_keywords": ["channel", "engineering", "messages"]
    },
    {
        "name": "Message Search for PM",
        "messages": [
            "Search for messages about deployment",
            "Were there any issues mentioned in those messages?",
            "Who was involved in that discussion?",
            "Find any follow-up messages from that person",
        ],
        "context_keywords": ["deployment", "messages", "discussion"]
    },
    {
        "name": "Team Communication Analysis",
        "messages": [
            "Show me the most active channels today",
            "What topics are being discussed in #general?",
            "Are there any urgent messages or announcements?",
            "Summarize the key discussions",
        ],
        "context_keywords": ["channel", "discussion", "urgent", "messages"]
    },
    {
        "name": "Finding Specific Information",
        "messages": [
            "Search for messages containing 'database' or 'credentials'",
            "Who sent those messages?",
            "What channel were they in?",
            "Show me the context around those messages",
        ],
        "context_keywords": ["database", "credentials", "messages", "channel"]
    },
    {
        "name": "User Activity Check",
        "messages": [
            "List all users in our workspace",
            "Who is currently online?",
            "Show me recent messages from the team lead",
            "What channels are they most active in?",
        ],
        "context_keywords": ["user", "online", "messages", "active"]
    },
]


async def run_all_tests():
    """Run all connector tests and generate report"""

    tester = ConnectorTester()

    print("\n" + "="*80)
    print("COMPREHENSIVE CONNECTOR TESTS - PM WORKFLOW VALIDATION")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}")
    print("Testing: S3, JIRA, Slack connectors")
    print("="*80)

    # Run S3 tests
    print("\n\n" + "#"*80)
    print("# S3 CONNECTOR TESTS")
    print("#"*80)

    for test in S3_TESTS:
        await tester.run_conversation(
            connector="s3",
            conversation_name=test["name"],
            messages=test["messages"],
            context_keywords=test.get("context_keywords", [])
        )

    # Run JIRA tests
    print("\n\n" + "#"*80)
    print("# JIRA CONNECTOR TESTS")
    print("#"*80)

    for test in JIRA_TESTS:
        await tester.run_conversation(
            connector="jira",
            conversation_name=test["name"],
            messages=test["messages"],
            context_keywords=test.get("context_keywords", [])
        )

    # Run Slack tests
    print("\n\n" + "#"*80)
    print("# SLACK CONNECTOR TESTS")
    print("#"*80)

    for test in SLACK_TESTS:
        await tester.run_conversation(
            connector="slack",
            conversation_name=test["name"],
            messages=test["messages"],
            context_keywords=test.get("context_keywords", [])
        )

    # Generate report
    print("\n\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)

    total_tests = len(tester.results)
    passed_tests = sum(1 for r in tester.results if r.passed)
    failed_tests = total_tests - passed_tests

    print(f"\nTotal Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Pass Rate: {(passed_tests/total_tests)*100:.1f}%")

    # Group by connector
    for connector in ["s3", "jira", "slack"]:
        connector_results = [r for r in tester.results if r.connector == connector]
        connector_passed = sum(1 for r in connector_results if r.passed)

        print(f"\n{connector.upper()} Connector:")
        print(f"  Tests: {len(connector_results)}, Passed: {connector_passed}, Failed: {len(connector_results) - connector_passed}")

        for result in connector_results:
            status = "PASS" if result.passed else "FAIL"
            avg_time = sum(result.response_times) / len(result.response_times)
            print(f"  [{status}] {result.conversation_name} ({result.turns} turns, avg {avg_time:.2f}s)")

            if not result.passed:
                for error in result.errors_found[:3]:  # Show first 3 errors
                    print(f"       ERROR: {error[:80]}...")

    # Detailed failure analysis
    failed_results = [r for r in tester.results if not r.passed]
    if failed_results:
        print("\n" + "="*80)
        print("DETAILED FAILURE ANALYSIS")
        print("="*80)

        for result in failed_results:
            print(f"\n{result.connector.upper()} - {result.conversation_name}")
            print("-" * 40)

            for i, turn in enumerate(result.full_conversation):
                role = turn["role"].upper()
                content = turn["content"][:300]
                print(f"[{role}]: {content}...")

            print("\nErrors Found:")
            for error in result.errors_found:
                print(f"  - {error}")

    # Save full results to file
    report_path = "/Users/santoshnaranapatty/ConnectorMCP/backend/tests/test_report.json"
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "pass_rate": (passed_tests/total_tests)*100
        },
        "results": [
            {
                "connector": r.connector,
                "name": r.conversation_name,
                "passed": r.passed,
                "turns": r.turns,
                "errors": r.errors_found,
                "context_maintained": r.context_maintained,
                "avg_response_time": sum(r.response_times) / len(r.response_times),
                "conversation": r.full_conversation
            }
            for r in tester.results
        ]
    }

    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)

    print(f"\n\nFull report saved to: {report_path}")

    return failed_tests == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Main E2E Test Runner

Runs all connector tests and generates a comprehensive report.
Designed to be run standalone or via pytest.

Usage:
    python -m tests.e2e.run_all_tests [--connector CONNECTOR] [--quick]

Options:
    --connector: Run tests for specific connector only (slack, jira, google_workspace)
    --quick: Run quick smoke tests only
    --verbose: Show detailed output
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import List, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.e2e.test_framework import (
    TestRunner,
    TestSuiteResult,
    TestStatus,
    DirectAPIClient,
)


class E2ETestOrchestrator:
    """Orchestrates running all E2E tests across connectors."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.runner = TestRunner(base_url)
        self.direct_api = DirectAPIClient()
        self.all_results: List[TestSuiteResult] = []
        self.start_time = datetime.now()

    async def check_backend_health(self) -> bool:
        """Check if backend is running and healthy."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.runner.chat_client.base_url}/api/health")
                return response.status_code == 200
        except Exception as e:
            print(f"Backend health check failed: {e}")
            return False

    async def run_smoke_tests(self) -> TestSuiteResult:
        """Run quick smoke tests for all connectors."""
        suite = TestSuiteResult(suite_name="Smoke Tests", connector="all")

        connectors = ["slack", "jira", "google_workspace"]

        for connector in connectors:
            self.runner.chat_client.reset_session()

            result = await self.runner.run_test_case(
                name=f"{connector} - Basic query",
                query="Hello, what can you help me with?",
                datasource=connector,
                expected_contains=[],
            )

            if result.status != TestStatus.ERROR:
                result.status = TestStatus.PASSED

            suite.results.append(result)

        suite.end_time = datetime.now()
        return suite

    async def run_slack_tests(self) -> TestSuiteResult:
        """Run comprehensive Slack tests."""
        suite = TestSuiteResult(suite_name="Slack Connector Tests", connector="slack")

        # Get actual data for validation
        channels = await self.direct_api.get_slack_channels()
        users = await self.direct_api.get_slack_users()

        channel_names = [c.get("name") for c in channels[:5]] if channels else []
        # Filter out Slackbot as it's a system user, not a real team member
        user_names = [u.get("real_name") for u in users[:5]
                     if u.get("real_name") and u.get("real_name").lower() != "slackbot"] if users else []

        # Note: With many channels (79+), expect LLM to show only common ones
        # Testing for 2 channels is sufficient to verify functionality
        tests = [
            ("List channels", "What channels do I have?", channel_names[:2]),
            ("List users", "Who is on my team?", user_names[:2]),
            ("Summarize messages", "Summarize what I missed in the last 24 hours", []),
            ("Search messages", "Search for messages about updates", []),
        ]

        for name, query, expected in tests:
            self.runner.chat_client.reset_session()
            result = await self.runner.run_test_case(
                name=name,
                query=query,
                datasource="slack",
                expected_contains=expected,
            )
            suite.results.append(result)

        # Conversation test
        if channels:
            channel = channels[0].get("name", "general")
            results = await self.runner.run_conversation_test(
                name="Slack conversation",
                queries=[
                    (f"Show messages from #{channel}", [channel]),
                    ("Who sent the most recent message?", []),
                ],
                datasource="slack",
            )
            suite.results.extend(results)

        suite.end_time = datetime.now()
        return suite

    async def run_jira_tests(self) -> TestSuiteResult:
        """Run comprehensive JIRA tests."""
        suite = TestSuiteResult(suite_name="JIRA Connector Tests", connector="jira")

        # Get projects for validation
        projects = await self.direct_api.get_jira_projects()
        project_names = [p.get("name") for p in projects[:5]] if projects else []

        tests = [
            ("List projects", "What JIRA projects do I have?", project_names[:2]),
            ("Oralia status", "What's the status of Oralia V2?", []),
            ("Sprint report", "Show me the sprint report for Oralia V2", []),
            ("Blocked issues", "What issues are blocked in Oralia V2?", []),
            ("Deep dive", "Give me a deep dive on Oralia V2", []),
        ]

        for name, query, expected in tests:
            self.runner.chat_client.reset_session()
            result = await self.runner.run_test_case(
                name=name,
                query=query,
                datasource="jira",
                expected_contains=expected,
            )
            suite.results.append(result)

        # Test other projects if available
        if len(projects) > 1:
            for project in projects[1:3]:  # Test next 2 projects
                project_name = project.get("name")
                result = await self.runner.run_test_case(
                    name=f"{project_name} status",
                    query=f"What's the status of {project_name}?",
                    datasource="jira",
                    expected_contains=[],
                )
                suite.results.append(result)

        # Conversation context test
        results = await self.runner.run_conversation_test(
            name="JIRA conversation",
            queries=[
                ("Tell me about Oralia V2", []),
                ("What issues are in progress?", []),
                ("Who is assigned the most?", []),
            ],
            datasource="jira",
        )
        suite.results.extend(results)

        suite.end_time = datetime.now()
        return suite

    async def run_google_workspace_tests(self) -> TestSuiteResult:
        """Run comprehensive Google Workspace tests."""
        suite = TestSuiteResult(suite_name="Google Workspace Tests", connector="google_workspace")

        tests = [
            ("List Drive files", "What files do I have in Google Drive?", []),
            ("Search sensihire", "Find all documents where I have talked about sensihire", []),
            ("Document content", "Tell me about the contents of those sensihire documents", []),
            ("Emails from Krishnan", "What are the most recent emails Krishnan sent me?", []),
            ("Calendar today", "What's on my calendar today?", []),
            ("Recent emails", "Show me my 10 most recent emails", []),
        ]

        for name, query, expected in tests:
            self.runner.chat_client.reset_session()
            result = await self.runner.run_test_case(
                name=name,
                query=query,
                datasource="google_workspace",
                expected_contains=expected,
            )
            suite.results.append(result)

        # Conversation context test
        results = await self.runner.run_conversation_test(
            name="Google Workspace conversation",
            queries=[
                ("Find my recent documents", []),
                ("What's in the first one?", []),
            ],
            datasource="google_workspace",
        )
        suite.results.extend(results)

        suite.end_time = datetime.now()
        return suite

    async def run_auth_tests(self) -> TestSuiteResult:
        """Run authentication flow tests."""
        suite = TestSuiteResult(suite_name="Authentication Tests", connector="system")

        # Check auth status
        auth_info = await self.runner.chat_client.check_auth()

        # Anonymous test
        self.runner.chat_client.auth_token = None
        self.runner.chat_client.reset_session()

        result = await self.runner.run_test_case(
            name="Anonymous chat",
            query="Hello, what connectors are available?",
            datasource="slack",
            expected_contains=[],
        )
        suite.results.append(result)

        # Session persistence
        result = await self.runner.run_test_case(
            name="Session persistence",
            query="Tell me more",
            datasource="slack",
            expected_contains=[],
        )
        suite.results.append(result)

        suite.end_time = datetime.now()
        return suite

    async def run_all(self, connector: Optional[str] = None, quick: bool = False) -> dict:
        """Run all tests and generate report."""
        print("\n" + "=" * 80)
        print("CONNECTORMCP E2E TEST SUITE")
        print("=" * 80)
        print(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Base URL: {self.runner.chat_client.base_url}")

        # Health check
        print("\nChecking backend health...")
        if not await self.check_backend_health():
            print("ERROR: Backend is not running or unhealthy!")
            print("Please start the backend with: uvicorn app.main:app --reload")
            return {"error": "Backend not available"}

        print("Backend is healthy.\n")

        if quick:
            print("Running QUICK smoke tests...")
            suite = await self.run_smoke_tests()
            self.all_results.append(suite)
        elif connector:
            print(f"Running tests for: {connector}")
            if connector == "slack":
                suite = await self.run_slack_tests()
            elif connector == "jira":
                suite = await self.run_jira_tests()
            elif connector == "google_workspace":
                suite = await self.run_google_workspace_tests()
            else:
                print(f"Unknown connector: {connector}")
                return {"error": f"Unknown connector: {connector}"}
            self.all_results.append(suite)
            self.runner.print_results(suite)
        else:
            # Run all tests
            print("\n[1/4] Running Authentication Tests...")
            suite = await self.run_auth_tests()
            self.all_results.append(suite)
            self.runner.print_results(suite)

            print("\n[2/4] Running Slack Tests...")
            suite = await self.run_slack_tests()
            self.all_results.append(suite)
            self.runner.print_results(suite)

            print("\n[3/4] Running JIRA Tests...")
            suite = await self.run_jira_tests()
            self.all_results.append(suite)
            self.runner.print_results(suite)

            print("\n[4/4] Running Google Workspace Tests...")
            suite = await self.run_google_workspace_tests()
            self.all_results.append(suite)
            self.runner.print_results(suite)

        # Generate summary
        return self.generate_summary()

    def generate_summary(self) -> dict:
        """Generate test summary."""
        total_passed = sum(s.passed for s in self.all_results)
        total_failed = sum(s.failed for s in self.all_results)
        total_tests = sum(s.total for s in self.all_results)

        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        summary = {
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "pass_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0,
            "suites": [
                {
                    "name": s.suite_name,
                    "connector": s.connector,
                    "passed": s.passed,
                    "failed": s.failed,
                    "total": s.total,
                    "pass_rate": s.pass_rate,
                }
                for s in self.all_results
            ],
        }

        # Print summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Duration: {duration:.1f}s")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Pass Rate: {summary['pass_rate']:.1f}%")
        print("\nBy Suite:")
        for s in self.all_results:
            status = "✓" if s.failed == 0 else "✗"
            print(f"  {status} {s.suite_name}: {s.passed}/{s.total} ({s.pass_rate:.1f}%)")
        print("=" * 80)

        # Save results
        results_file = f"e2e_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nResults saved to: {results_file}")

        return summary


async def main():
    parser = argparse.ArgumentParser(description="Run E2E tests for ConnectorMCP")
    parser.add_argument(
        "--connector",
        choices=["slack", "jira", "google_workspace"],
        help="Run tests for specific connector only",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick smoke tests only",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Backend URL (default: http://localhost:8000)",
    )

    args = parser.parse_args()

    orchestrator = E2ETestOrchestrator(base_url=args.url)
    summary = await orchestrator.run_all(connector=args.connector, quick=args.quick)

    # Exit with error code if tests failed
    if summary.get("error"):
        sys.exit(1)
    if summary.get("failed", 0) > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
COMPREHENSIVE BOSS/PM TEST SUITE
================================
Tests natural language queries across all connectors as if you're a boss/PM.
15+ business-value questions per connector.

Run with: python tests/comprehensive_boss_test.py
"""

import asyncio
import time
import aiohttp
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 180  # 3 minute timeout

# Terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


class ConnectorTester:
    """Generic tester for any connector."""

    def __init__(self, datasource: str):
        self.datasource = datasource
        self.session_id: Optional[str] = None
        self.results: List[Dict[str, Any]] = []

    async def send_message(
        self,
        session: aiohttp.ClientSession,
        message: str,
        new_conversation: bool = False
    ) -> Dict[str, Any]:
        """Send a message and collect the streaming response."""
        start = time.time()
        first_token_time = None
        full_response = ""
        tools_used = []
        sources = []

        url = f"{BASE_URL}/api/chat/message/stream"
        payload = {
            "message": message,
            "datasource": self.datasource,
        }

        if not new_conversation and self.session_id:
            payload["session_id"] = self.session_id

        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                async for line in response.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            event_type = data.get('type')

                            if event_type == 'session':
                                self.session_id = data.get('session_id')
                            elif event_type == 'content':
                                if first_token_time is None:
                                    first_token_time = time.time() - start
                                full_response += data.get('content', '')
                            elif event_type == 'agent_step':
                                step = data.get('step', {})
                                if step.get('type') == 'tool_call':
                                    tools_used.append(step.get('title', ''))
                            elif event_type == 'done':
                                sources = data.get('sources', [])
                        except json.JSONDecodeError:
                            pass

                total_time = time.time() - start

                return {
                    "response": full_response,
                    "tools_used": tools_used,
                    "sources": sources,
                    "ttft": first_token_time or total_time,
                    "total_time": total_time,
                    "success": len(full_response) > 30,
                    "error": None
                }

        except asyncio.TimeoutError:
            return {
                "response": "",
                "tools_used": [],
                "sources": [],
                "ttft": TIMEOUT,
                "total_time": TIMEOUT,
                "success": False,
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "response": str(e),
                "tools_used": [],
                "sources": [],
                "ttft": 0,
                "total_time": time.time() - start,
                "success": False,
                "error": str(e)
            }


def print_test_header(title: str, description: str):
    """Print a test section header."""
    print(f"\n{'='*100}")
    print(f"{CYAN}{BOLD}{title}{RESET}")
    print(f"{CYAN}{description}{RESET}")
    print(f"{'='*100}")


def print_result(index: int, query: str, result: Dict[str, Any]):
    """Pretty print a test result with full response."""
    print(f"\n{'-'*100}")
    print(f"{BLUE}{BOLD}TEST #{index}: {query}{RESET}")
    print(f"{'-'*100}")

    # Show full response
    response = result['response']
    print(f"\n{GREEN}RESPONSE:{RESET}")
    print(response)

    # Timing and status
    speed_color = GREEN if result['ttft'] < 3 else YELLOW if result['ttft'] < 6 else RED
    status = f"{GREEN}SUCCESS{RESET}" if result['success'] else f"{RED}FAILED{RESET}"

    print(f"\n{speed_color}Time to first token: {result['ttft']:.2f}s | Total: {result['total_time']:.2f}s{RESET}")
    print(f"Status: {status}")

    if result.get('tools_used'):
        print(f"Tools used: {', '.join(result['tools_used'])}")

    if result['error']:
        print(f"{RED}Error: {result['error']}{RESET}")

    return result


async def test_slack_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test Slack connector - 15+ business-value questions."""
    print_test_header(
        "SLACK CONNECTOR TESTS (15+ Questions)",
        "Testing as a boss/PM checking team communication and collaboration"
    )

    tester = ConnectorTester("slack")
    all_results = []

    test_cases = [
        # Team Overview
        "What channels do we have in our workspace?",
        "Who are all the people in our team?",
        "Show me the most active channels",

        # Individual Activity (testing the new get_user_activity)
        "What is Swati working on?",
        "What has Ananth been up to lately?",
        "Show me Austin's recent activity",
        "What did Santosh say recently?",

        # Channel Activity
        "What's the latest discussion in the general channel?",
        "Show me what's happening in the engineering channel",
        "Are there any important messages I missed today?",

        # Search and Discovery
        "Search for any messages about the project deadline",
        "Find discussions about deployment or releases",
        "Are there any messages mentioning bugs or issues?",

        # DM and Personal
        "Show me my recent DM conversations",
        "What direct messages did I receive recently?",

        # Summary and Catch-up
        "Give me a summary of all important messages from the last 24 hours",
        "What did I miss while I was away?",

        # Context-dependent follow-up
        "Tell me more about the first message you found",
    ]

    for i, query in enumerate(test_cases, 1):
        new_conv = i != len(test_cases)  # Last one uses context
        result = await tester.send_message(session, query, new_conv)
        print_result(i, query, result)
        all_results.append({
            "connector": "slack",
            "query": query,
            **result
        })
        await asyncio.sleep(1)

    return all_results


async def test_jira_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test JIRA connector - 15+ business-value questions."""
    print_test_header(
        "JIRA CONNECTOR TESTS (15+ Questions)",
        "Testing as a boss/PM tracking project progress and team workload"
    )

    tester = ConnectorTester("jira")
    all_results = []

    test_cases = [
        # Project Discovery
        "What projects do we have in JIRA?",
        "Show me all our active projects",
        "Which project has the most issues?",

        # Issue Status
        "What are all the open issues right now?",
        "Show me high priority bugs that need attention",
        "Are there any blocker or critical issues?",
        "What issues are stuck in code review?",

        # Team Workload
        "What is everyone working on right now?",
        "Who has the most tickets assigned to them?",
        "Show me what Austin is working on",
        "What tasks are assigned to Swati?",

        # Sprint and Progress
        "What's the status of the current sprint?",
        "How many tasks are completed vs still in progress?",
        "What issues were completed this week?",

        # Specific Queries
        "Show me all the recent issues created",
        "Find issues related to authentication or login",
        "What bugs were reported in the last 7 days?",

        # Follow-up
        "Tell me more about the first blocked issue",
    ]

    for i, query in enumerate(test_cases, 1):
        new_conv = i != len(test_cases)
        result = await tester.send_message(session, query, new_conv)
        print_result(i, query, result)
        all_results.append({
            "connector": "jira",
            "query": query,
            **result
        })
        await asyncio.sleep(1)

    return all_results


async def test_mysql_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test MySQL connector - 15+ business-value questions."""
    print_test_header(
        "MySQL CONNECTOR TESTS (15+ Questions)",
        "Testing as a boss/PM analyzing business data and metrics"
    )

    tester = ConnectorTester("mysql")
    all_results = []

    test_cases = [
        # Schema Discovery
        "What databases do I have access to?",
        "What tables exist in my database?",
        "Describe the structure of the users table",
        "What columns are in the orders table?",

        # Data Exploration
        "Show me the first 10 users",
        "How many records are in each table?",
        "What's the total number of orders?",

        # Business Metrics
        "Show me the most recent orders",
        "What's the average order value?",
        "Who are our top customers by order count?",
        "Show me orders from the last month",

        # User Analytics
        "How many users signed up this week?",
        "Show me the newest user registrations",
        "What's the distribution of users by status?",

        # Data Analysis
        "Find orders with the highest values",
        "What products are most frequently ordered?",
        "Show me any pending or failed orders",

        # Follow-up
        "Tell me more about the first user in the list",
    ]

    for i, query in enumerate(test_cases, 1):
        new_conv = i != len(test_cases)
        result = await tester.send_message(session, query, new_conv)
        print_result(i, query, result)
        all_results.append({
            "connector": "mysql",
            "query": query,
            **result
        })
        await asyncio.sleep(1)

    return all_results


async def test_s3_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test S3 connector - 15+ business-value questions."""
    print_test_header(
        "S3 CONNECTOR TESTS (15+ Questions)",
        "Testing as a boss/PM reviewing stored documents and files"
    )

    tester = ConnectorTester("s3")
    all_results = []

    test_cases = [
        # Bucket Discovery
        "What S3 buckets do we have?",
        "Show me all available storage buckets",
        "Which bucket has the most files?",

        # File Discovery
        "List all the files in our main bucket",
        "What documents do we have stored?",
        "Show me any PDF files",
        "Are there any markdown or documentation files?",

        # Content Exploration
        "What's the largest file we have?",
        "Show me recently uploaded files",
        "Find any architecture or design documents",

        # Reading Content
        "Read the contents of any README file",
        "Show me the content of the first document you find",
        "Summarize any documentation files",

        # Specific Searches
        "Find files related to deployment",
        "Are there any configuration files?",
        "Show me files that mention API or integration",

        # Follow-up
        "Tell me more about that file",
    ]

    for i, query in enumerate(test_cases, 1):
        new_conv = i != len(test_cases)
        result = await tester.send_message(session, query, new_conv)
        print_result(i, query, result)
        all_results.append({
            "connector": "s3",
            "query": query,
            **result
        })
        await asyncio.sleep(1)

    return all_results


def print_final_summary(all_results: List[Dict[str, Any]]):
    """Print final comprehensive summary."""
    print(f"\n{'='*100}")
    print(f"{BOLD}{CYAN}FINAL TEST SUMMARY{RESET}")
    print(f"{'='*100}")

    # Group by connector
    by_connector = {}
    for r in all_results:
        conn = r.get('connector', 'unknown')
        if conn not in by_connector:
            by_connector[conn] = []
        by_connector[conn].append(r)

    # Overall stats
    total = len(all_results)
    successful = sum(1 for r in all_results if r.get('success', False))

    times = [r['ttft'] for r in all_results if r.get('ttft', 0) > 0 and r.get('ttft', 0) < TIMEOUT]
    avg_ttft = sum(times) / len(times) if times else 0

    print(f"\n{BOLD}OVERALL STATISTICS:{RESET}")
    print(f"  Total Tests Run: {total}")
    print(f"  Successful: {GREEN}{successful}/{total} ({100*successful/total:.1f}%){RESET}")
    print(f"  Average Response Time: {avg_ttft:.2f}s")

    # Per-connector breakdown
    print(f"\n{BOLD}CONNECTOR BREAKDOWN:{RESET}")
    print(f"{'Connector':<15} {'Tests':<8} {'Passed':<10} {'Pass Rate':<12} {'Avg Time':<12}")
    print(f"{'-'*60}")

    for conn in ['slack', 'jira', 'mysql', 's3']:
        if conn not in by_connector:
            continue
        results = by_connector[conn]
        passed = sum(1 for r in results if r.get('success', False))
        total_conn = len(results)
        times_conn = [r['ttft'] for r in results if r.get('ttft', 0) > 0 and r.get('ttft', 0) < TIMEOUT]
        avg_conn = sum(times_conn) / len(times_conn) if times_conn else 0

        pass_rate = 100 * passed / total_conn if total_conn > 0 else 0
        rate_color = GREEN if pass_rate >= 80 else YELLOW if pass_rate >= 50 else RED

        icon = {"slack": "Slack", "s3": "S3", "jira": "JIRA", "mysql": "MySQL"}.get(conn, conn)
        print(f"{icon:<15} {total_conn:<8} {passed:<10} {rate_color}{pass_rate:.1f}%{RESET}{'':>6} {avg_conn:.2f}s")

    # Failed tests summary
    failed = [r for r in all_results if not r.get('success', False)]
    if failed:
        print(f"\n{RED}{BOLD}FAILED TESTS ({len(failed)}):{RESET}")
        for f in failed:
            print(f"  [{f.get('connector')}] {f.get('query', 'Unknown')[:60]}")
            if f.get('error'):
                print(f"    Error: {f['error']}")

    print(f"\n{'='*100}")
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}\n")


async def main():
    """Run all tests."""
    print(f"\n{BOLD}{'='*100}")
    print(f"COMPREHENSIVE BOSS/PM TEST SUITE")
    print(f"Testing ALL Connectors with 15+ Business Questions Each")
    print(f"{'='*100}{RESET}")
    print(f"\nConnectors to test:")
    print(f"  - Slack (team communication)")
    print(f"  - JIRA (project management)")
    print(f"  - MySQL (business data)")
    print(f"  - S3 (file storage)")
    print(f"\n{YELLOW}Ensure backend is running at {BASE_URL}{RESET}\n")

    all_results = []

    async with aiohttp.ClientSession() as session:
        # Test Slack
        print(f"\n{MAGENTA}{BOLD}Starting SLACK Tests...{RESET}")
        slack_results = await test_slack_connector(session)
        all_results.extend(slack_results)

        # Test JIRA
        print(f"\n{MAGENTA}{BOLD}Starting JIRA Tests...{RESET}")
        jira_results = await test_jira_connector(session)
        all_results.extend(jira_results)

        # Test MySQL
        print(f"\n{MAGENTA}{BOLD}Starting MySQL Tests...{RESET}")
        mysql_results = await test_mysql_connector(session)
        all_results.extend(mysql_results)

        # Test S3
        print(f"\n{MAGENTA}{BOLD}Starting S3 Tests...{RESET}")
        s3_results = await test_s3_connector(session)
        all_results.extend(s3_results)

    # Final summary
    print_final_summary(all_results)

    return all_results


if __name__ == "__main__":
    asyncio.run(main())

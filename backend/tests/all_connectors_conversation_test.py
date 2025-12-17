#!/usr/bin/env python3
"""
Comprehensive Conversational Test Suite for All Connectors

Tests natural language queries across:
- Slack (messages, DMs, channels)
- S3 (buckets, files, content)
- JIRA (projects, issues, sprints)
- MySQL (tables, queries, data)

Validates:
1. Tool routing correctness
2. Natural language understanding
3. Multi-turn conversation context
4. Response quality and completeness
"""

import asyncio
import time
import aiohttp
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 180  # 3 minute timeout for complex queries

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
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}{title}{RESET}")
    print(f"{CYAN}{description}{RESET}")
    print(f"{'='*80}")


def print_result(query: str, result: Dict[str, Any], expected_behavior: str = None):
    """Pretty print a test result."""
    print(f"\n{BLUE}{BOLD}👤 Query:{RESET} \"{query}\"")
    
    if expected_behavior:
        print(f"{DIM}   Expected: {expected_behavior}{RESET}")
    
    # Show response (truncated)
    response = result['response']
    if len(response) > 1500:
        print(f"\n{GREEN}🤖 Response:{RESET}")
        print(f"   {response[:1500]}...")
        print(f"   {DIM}[Truncated - {len(response)} chars total]{RESET}")
    else:
        print(f"\n{GREEN}🤖 Response:{RESET}")
        print(f"   {response}")
    
    # Timing
    speed_color = GREEN if result['ttft'] < 3 else YELLOW if result['ttft'] < 6 else RED
    status = f"{GREEN}✓ Success{RESET}" if result['success'] else f"{RED}✗ Failed{RESET}"
    
    print(f"\n   {speed_color}⏱️ TTFT: {result['ttft']:.2f}s | Total: {result['total_time']:.2f}s{RESET} | {status}")
    
    if result['error']:
        print(f"   {RED}Error: {result['error']}{RESET}")
    
    return result


async def test_s3_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test S3 connector with comprehensive queries."""
    print_test_header("📦 S3 CONNECTOR TESTS", "Testing file storage discovery and content retrieval")
    
    tester = ConnectorTester("s3")
    all_results = []
    
    test_cases = [
        # Discovery queries
        {
            "query": "What buckets do I have?",
            "behavior": "Should list all S3 buckets",
            "new_conv": True
        },
        {
            "query": "Show me the contents of my main bucket",
            "behavior": "Should list objects in a bucket",
            "new_conv": True
        },
        {
            "query": "What files do I have stored?",
            "behavior": "Should list files across buckets",
            "new_conv": True
        },
        
        # Content exploration
        {
            "query": "Are there any documents or PDFs in my storage?",
            "behavior": "Should search for document files",
            "new_conv": True
        },
        {
            "query": "Show me any markdown or text files",
            "behavior": "Should find .md and .txt files",
            "new_conv": True
        },
        {
            "query": "What's the largest file I have?",
            "behavior": "Should analyze file sizes",
            "new_conv": True
        },
        
        # Content reading
        {
            "query": "Read the first document you find",
            "behavior": "Should read file content",
            "new_conv": True
        },
        {
            "query": "Summarize the contents of any architecture docs",
            "behavior": "Should read and summarize",
            "new_conv": True
        },
        
        # Multi-turn
        {
            "query": "List all files in bideclaudetest bucket",
            "behavior": "Should list specific bucket",
            "new_conv": True
        },
        {
            "query": "Tell me more about the first file",
            "behavior": "Should use context from previous query",
            "new_conv": False
        },
    ]
    
    for tc in test_cases:
        print(f"\n{YELLOW}📌 Test: {tc['behavior']}{RESET}")
        result = await tester.send_message(session, tc["query"], tc.get("new_conv", True))
        print_result(tc["query"], result, tc["behavior"])
        all_results.append({
            "connector": "s3",
            "query": tc["query"],
            "expected": tc["behavior"],
            **result
        })
        await asyncio.sleep(1)
    
    return all_results


async def test_jira_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test JIRA connector with comprehensive queries."""
    print_test_header("🎫 JIRA CONNECTOR TESTS", "Testing project and issue management queries")
    
    tester = ConnectorTester("jira")
    all_results = []
    
    test_cases = [
        # Project discovery
        {
            "query": "What projects do we have in JIRA?",
            "behavior": "Should list all JIRA projects",
            "new_conv": True
        },
        {
            "query": "Show me all active projects",
            "behavior": "Should list active projects",
            "new_conv": True
        },
        
        # Issue queries
        {
            "query": "What are the open issues?",
            "behavior": "Should query open issues",
            "new_conv": True
        },
        {
            "query": "Show me high priority bugs",
            "behavior": "Should filter by priority and type",
            "new_conv": True
        },
        {
            "query": "What issues are assigned to me?",
            "behavior": "Should filter by assignee",
            "new_conv": True
        },
        {
            "query": "List all blockers and critical issues",
            "behavior": "Should find blocking issues",
            "new_conv": True
        },
        
        # Sprint and status
        {
            "query": "What's the status of the current sprint?",
            "behavior": "Should show sprint status",
            "new_conv": True
        },
        {
            "query": "How many tasks are completed vs in progress?",
            "behavior": "Should aggregate status",
            "new_conv": True
        },
        
        # Team queries
        {
            "query": "Who has the most tickets assigned?",
            "behavior": "Should analyze assignments",
            "new_conv": True
        },
        {
            "query": "What is each team member working on?",
            "behavior": "Should list assignee workloads",
            "new_conv": True
        },
        
        # Multi-turn
        {
            "query": "Show me the latest issues created",
            "behavior": "Should query recent issues",
            "new_conv": True
        },
        {
            "query": "Tell me more about the first one",
            "behavior": "Should use context",
            "new_conv": False
        },
    ]
    
    for tc in test_cases:
        print(f"\n{YELLOW}📌 Test: {tc['behavior']}{RESET}")
        result = await tester.send_message(session, tc["query"], tc.get("new_conv", True))
        print_result(tc["query"], result, tc["behavior"])
        all_results.append({
            "connector": "jira",
            "query": tc["query"],
            "expected": tc["behavior"],
            **result
        })
        await asyncio.sleep(1)
    
    return all_results


async def test_mysql_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test MySQL connector with comprehensive queries."""
    print_test_header("🗄️ MySQL CONNECTOR TESTS", "Testing database exploration and queries")
    
    tester = ConnectorTester("mysql")
    all_results = []
    
    test_cases = [
        # Schema discovery
        {
            "query": "What databases do I have?",
            "behavior": "Should list databases",
            "new_conv": True
        },
        {
            "query": "What tables exist in the database?",
            "behavior": "Should list tables",
            "new_conv": True
        },
        {
            "query": "Describe the structure of the users table",
            "behavior": "Should show table schema",
            "new_conv": True
        },
        
        # Data exploration
        {
            "query": "Show me the first 10 rows from users",
            "behavior": "Should query with limit",
            "new_conv": True
        },
        {
            "query": "How many records are in each table?",
            "behavior": "Should count records",
            "new_conv": True
        },
        {
            "query": "What are the column names and types in orders table?",
            "behavior": "Should describe columns",
            "new_conv": True
        },
        
        # Natural language queries
        {
            "query": "Show me the latest orders",
            "behavior": "Should query with ordering",
            "new_conv": True
        },
        {
            "query": "Find all users who signed up this month",
            "behavior": "Should filter by date",
            "new_conv": True
        },
        {
            "query": "What's the average order value?",
            "behavior": "Should calculate aggregate",
            "new_conv": True
        },
        
        # Multi-turn
        {
            "query": "List all tables",
            "behavior": "Should list tables",
            "new_conv": True
        },
        {
            "query": "Tell me about the first table",
            "behavior": "Should use context",
            "new_conv": False
        },
    ]
    
    for tc in test_cases:
        print(f"\n{YELLOW}📌 Test: {tc['behavior']}{RESET}")
        result = await tester.send_message(session, tc["query"], tc.get("new_conv", True))
        print_result(tc["query"], result, tc["behavior"])
        all_results.append({
            "connector": "mysql",
            "query": tc["query"],
            "expected": tc["behavior"],
            **result
        })
        await asyncio.sleep(1)
    
    return all_results


async def test_slack_connector(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """Test Slack connector with key queries (subset of full test)."""
    print_test_header("💬 SLACK CONNECTOR TESTS", "Testing messaging and workspace queries")
    
    tester = ConnectorTester("slack")
    all_results = []
    
    test_cases = [
        # Workspace discovery
        {
            "query": "What channels do we have?",
            "behavior": "Should list channels",
            "new_conv": True
        },
        {
            "query": "Who are the people in this workspace?",
            "behavior": "Should list users",
            "new_conv": True
        },
        {
            "query": "Show me my DM conversations",
            "behavior": "Should list DMs",
            "new_conv": True
        },
        
        # Message queries
        {
            "query": "What messages did I miss today?",
            "behavior": "Should summarize recent messages",
            "new_conv": True
        },
        {
            "query": "Search for any messages about the project",
            "behavior": "Should search messages",
            "new_conv": True
        },
        
        # Person-specific
        {
            "query": "What did Ananth say recently?",
            "behavior": "Should read DM with user",
            "new_conv": True
        },
        
        # Complex summarization
        {
            "query": "Summarize all important messages from yesterday across DMs and channels",
            "behavior": "Should multi-source summarize",
            "new_conv": True
        },
    ]
    
    for tc in test_cases:
        print(f"\n{YELLOW}📌 Test: {tc['behavior']}{RESET}")
        result = await tester.send_message(session, tc["query"], tc.get("new_conv", True))
        print_result(tc["query"], result, tc["behavior"])
        all_results.append({
            "connector": "slack",
            "query": tc["query"],
            "expected": tc["behavior"],
            **result
        })
        await asyncio.sleep(1)
    
    return all_results


def print_comprehensive_summary(all_results: List[Dict[str, Any]]):
    """Print comprehensive test summary across all connectors."""
    print(f"\n{'='*80}")
    print(f"{BOLD}📊 COMPREHENSIVE TEST SUMMARY - ALL CONNECTORS{RESET}")
    print(f"{'='*80}")
    
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
    
    print(f"\n{BOLD}Overall Statistics:{RESET}")
    print(f"  Total Tests: {total}")
    print(f"  Successful: {GREEN}{successful}/{total} ({100*successful/total:.1f}%){RESET}")
    print(f"  Average TTFT: {avg_ttft:.2f}s")
    
    # Per-connector stats
    print(f"\n{BOLD}Results by Connector:{RESET}")
    print(f"{'Connector':<12} {'Tests':<8} {'Passed':<10} {'Avg TTFT':<12} {'Status':<15}")
    print(f"{'-'*60}")
    
    for conn, results in by_connector.items():
        passed = sum(1 for r in results if r.get('success', False))
        total_conn = len(results)
        times_conn = [r['ttft'] for r in results if r.get('ttft', 0) > 0 and r.get('ttft', 0) < TIMEOUT]
        avg_conn = sum(times_conn) / len(times_conn) if times_conn else 0
        
        pass_rate = passed / total_conn if total_conn > 0 else 0
        status_color = GREEN if pass_rate >= 0.8 else YELLOW if pass_rate >= 0.5 else RED
        status = "✓ Good" if pass_rate >= 0.8 else "⚠ Issues" if pass_rate >= 0.5 else "✗ Problems"
        
        icon = {"slack": "💬", "s3": "📦", "jira": "🎫", "mysql": "🗄️"}.get(conn, "📌")
        
        print(f"{icon} {conn:<10} {total_conn:<8} {status_color}{passed}/{total_conn:<8}{RESET} {avg_conn:.2f}s{' '*6} {status_color}{status}{RESET}")
    
    # Speed distribution
    fast = sum(1 for r in all_results if r.get('ttft', 999) < 3)
    medium = sum(1 for r in all_results if 3 <= r.get('ttft', 999) < 8)
    slow = sum(1 for r in all_results if r.get('ttft', 0) >= 8)
    
    print(f"\n{BOLD}Response Speed Distribution:{RESET}")
    print(f"  {GREEN}⚡ Fast (<3s):{RESET} {fast} tests")
    print(f"  {YELLOW}⏱️  Medium (3-8s):{RESET} {medium} tests")
    print(f"  {RED}🐢 Slow (>8s):{RESET} {slow} tests")
    
    # Failed tests
    failed = [r for r in all_results if not r.get('success', False)]
    if failed:
        print(f"\n{RED}{BOLD}Failed Tests ({len(failed)}):{RESET}")
        for f in failed[:10]:
            print(f"  ✗ [{f.get('connector')}] {f.get('query', 'Unknown')[:50]}...")
            if f.get('error'):
                print(f"    Error: {f['error']}")
    
    # Overall rating
    success_rate = successful / total if total > 0 else 0
    print(f"\n{BOLD}🎯 Overall Platform Rating:{RESET}")
    
    if success_rate >= 0.9 and avg_ttft < 3:
        print(f"  {GREEN}⭐⭐⭐⭐⭐ EXCELLENT - All connectors production ready!{RESET}")
    elif success_rate >= 0.8 and avg_ttft < 5:
        print(f"  {GREEN}⭐⭐⭐⭐ GOOD - Most connectors working well{RESET}")
    elif success_rate >= 0.6:
        print(f"  {YELLOW}⭐⭐⭐ ACCEPTABLE - Some connectors need work{RESET}")
    elif success_rate >= 0.4:
        print(f"  {YELLOW}⭐⭐ NEEDS IMPROVEMENT - Multiple issues{RESET}")
    else:
        print(f"  {RED}⭐ CRITICAL - Major problems detected{RESET}")
    
    # Connector-specific recommendations
    print(f"\n{BOLD}Connector Status:{RESET}")
    for conn, results in by_connector.items():
        passed = sum(1 for r in results if r.get('success', False))
        total_conn = len(results)
        pass_rate = passed / total_conn if total_conn > 0 else 0
        
        icon = {"slack": "💬", "s3": "📦", "jira": "🎫", "mysql": "🗄️"}.get(conn, "📌")
        
        if pass_rate >= 0.9:
            print(f"  {icon} {conn.upper()}: {GREEN}✓ Production Ready{RESET}")
        elif pass_rate >= 0.7:
            print(f"  {icon} {conn.upper()}: {GREEN}✓ Good with minor issues{RESET}")
        elif pass_rate >= 0.5:
            print(f"  {icon} {conn.upper()}: {YELLOW}⚠ Needs optimization{RESET}")
        else:
            print(f"  {icon} {conn.upper()}: {RED}✗ Requires attention{RESET}")
    
    print(f"\n{'='*80}")
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")


async def main():
    """Run comprehensive tests across all connectors."""
    print(f"\n{BOLD}{'='*80}")
    print(f"🚀 MOSAIC COMPREHENSIVE CONNECTOR TEST SUITE")
    print(f"{'='*80}{RESET}")
    print(f"\nTesting all connectors for conversational ability:")
    print(f"  📦 S3 - File storage and content")
    print(f"  🎫 JIRA - Project and issue management")
    print(f"  🗄️  MySQL - Database queries")
    print(f"  💬 Slack - Messaging and workspace")
    print(f"\n{YELLOW}⚠️  Ensure backend is running and all credentials are configured.{RESET}\n")
    
    all_results = []
    
    async with aiohttp.ClientSession() as session:
        # Test each connector
        print(f"\n{MAGENTA}{BOLD}Starting S3 Tests...{RESET}")
        s3_results = await test_s3_connector(session)
        all_results.extend(s3_results)
        
        print(f"\n{MAGENTA}{BOLD}Starting JIRA Tests...{RESET}")
        jira_results = await test_jira_connector(session)
        all_results.extend(jira_results)
        
        print(f"\n{MAGENTA}{BOLD}Starting MySQL Tests...{RESET}")
        mysql_results = await test_mysql_connector(session)
        all_results.extend(mysql_results)
        
        print(f"\n{MAGENTA}{BOLD}Starting Slack Tests...{RESET}")
        slack_results = await test_slack_connector(session)
        all_results.extend(slack_results)
    
    # Print comprehensive summary
    print_comprehensive_summary(all_results)


if __name__ == "__main__":
    asyncio.run(main())



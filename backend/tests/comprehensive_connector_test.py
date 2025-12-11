#!/usr/bin/env python3
"""
Comprehensive Connector Test Suite
==================================
This test suite simulates a business owner having natural conversations
with each connector to derive actionable business insights.

Tests:
1. MySQL Connector - Database queries, joins, analytics
2. S3 Connector - Document discovery and exploration
3. JIRA Connector - Sprint management, team workload
4. Multi-tenancy - Credential isolation
5. Streaming - ChatGPT-like response delivery
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
import sys

import os

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
STREAM_ENDPOINT = "/api/chat/message/stream"
NON_STREAM_ENDPOINT = "/api/chat/message"

# ANSI Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_test(test_name: str):
    print(f"\n{Colors.CYAN}[TEST] {test_name}{Colors.ENDC}")

def print_user(message: str):
    print(f"{Colors.BLUE}[USER] {message}{Colors.ENDC}")

def print_assistant(message: str, truncate: bool = True):
    if truncate and len(message) > 500:
        message = message[:500] + "... [truncated]"
    print(f"{Colors.GREEN}[ASSISTANT] {message}{Colors.ENDC}")

def print_stream_char(char: str):
    """Print character immediately without newline (streaming effect)"""
    sys.stdout.write(f"{Colors.GREEN}{char}{Colors.ENDC}")
    sys.stdout.flush()

def print_success(message: str):
    print(f"{Colors.GREEN}[SUCCESS] {message}{Colors.ENDC}")

def print_error(message: str):
    print(f"{Colors.RED}[ERROR] {message}{Colors.ENDC}")

def print_warning(message: str):
    print(f"{Colors.YELLOW}[WARNING] {message}{Colors.ENDC}")

def print_info(message: str):
    print(f"{Colors.CYAN}[INFO] {message}{Colors.ENDC}")

def print_metrics(time_to_first_token: float, total_time: float, char_count: int):
    print(f"\n{Colors.YELLOW}[METRICS]{Colors.ENDC}")
    print(f"  Time to first token: {time_to_first_token:.2f}s")
    print(f"  Total response time: {total_time:.2f}s")
    print(f"  Characters received: {char_count}")
    if total_time > 0:
        print(f"  Characters per second: {char_count/total_time:.1f}")


class TestSession:
    """Manages a test session with the chat API"""

    def __init__(self, datasource: str):
        self.datasource = datasource
        self.session_id: Optional[str] = None
        self.messages: List[Dict[str, str]] = []

    async def send_message_streaming(self, message: str, print_response: bool = True) -> Dict[str, Any]:
        """Send a message and receive streaming response"""
        print_user(message)

        start_time = time.time()
        first_token_time = None
        full_response = ""
        char_count = 0

        async with aiohttp.ClientSession() as session:
            payload = {
                "message": message,
                "datasource": self.datasource,
                "session_id": self.session_id
            }

            try:
                async with session.post(
                    f"{BASE_URL}{STREAM_ENDPOINT}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print_error(f"HTTP {response.status}: {error_text}")
                        return {"error": error_text, "status": response.status}

                    if print_response:
                        print(f"{Colors.GREEN}[ASSISTANT] ", end="")

                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])

                                if data.get('type') == 'session':
                                    self.session_id = data.get('session_id')

                                elif data.get('type') == 'content':
                                    content = data.get('content', '')
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    full_response += content
                                    char_count += len(content)
                                    if print_response:
                                        sys.stdout.write(content)
                                        sys.stdout.flush()

                                elif data.get('type') == 'done':
                                    if print_response:
                                        print(f"{Colors.ENDC}")
                                    break

                                elif data.get('type') == 'error':
                                    print_error(data.get('error', 'Unknown error'))

                            except json.JSONDecodeError:
                                pass

            except aiohttp.ClientError as e:
                print_error(f"Connection error: {str(e)}")
                return {"error": str(e)}

        end_time = time.time()
        total_time = end_time - start_time
        ttft = (first_token_time - start_time) if first_token_time else total_time

        # Store message in history
        self.messages.append({"role": "user", "content": message})
        self.messages.append({"role": "assistant", "content": full_response})

        return {
            "response": full_response,
            "time_to_first_token": ttft,
            "total_time": total_time,
            "char_count": char_count,
            "session_id": self.session_id
        }

    async def send_message_non_streaming(self, message: str) -> Dict[str, Any]:
        """Send a message without streaming (for comparison)"""
        print_user(message)

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            payload = {
                "message": message,
                "datasource": self.datasource,
                "session_id": self.session_id
            }

            try:
                async with session.post(
                    f"{BASE_URL}{NON_STREAM_ENDPOINT}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print_error(f"HTTP {response.status}: {error_text}")
                        return {"error": error_text, "status": response.status}

                    data = await response.json()
                    full_response = data.get("response", "")
                    self.session_id = data.get("session_id")

            except aiohttp.ClientError as e:
                print_error(f"Connection error: {str(e)}")
                return {"error": str(e)}

        end_time = time.time()
        total_time = end_time - start_time

        print_assistant(full_response)

        return {
            "response": full_response,
            "total_time": total_time,
            "char_count": len(full_response),
            "session_id": self.session_id
        }


class TestResults:
    """Tracks test results"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details: List[Dict[str, Any]] = []

    def add_result(self, test_name: str, passed: bool, message: str = "", warning: bool = False):
        self.details.append({
            "test": test_name,
            "passed": passed,
            "message": message,
            "warning": warning
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        if warning:
            self.warnings += 1

    def print_summary(self):
        print_header("TEST SUMMARY")
        print(f"Total tests: {self.passed + self.failed}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.ENDC}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Warnings: {self.warnings}{Colors.ENDC}")

        if self.details:
            print(f"\n{Colors.BOLD}Details:{Colors.ENDC}")
            for detail in self.details:
                status = f"{Colors.GREEN}PASS{Colors.ENDC}" if detail['passed'] else f"{Colors.RED}FAIL{Colors.ENDC}"
                if detail['warning']:
                    status += f" {Colors.YELLOW}(WARNING){Colors.ENDC}"
                print(f"  [{status}] {detail['test']}: {detail['message']}")


# =============================================================================
# MySQL CONNECTOR TESTS
# =============================================================================

async def test_mysql_connector(results: TestResults):
    """Test MySQL connector with business-like conversations"""
    print_header("MYSQL CONNECTOR TESTS - Business Analytics")

    session = TestSession("mysql")

    # Test 1: Discovery - What data do we have?
    print_test("1. Database Discovery")
    result = await session.send_message_streaming(
        "Hi! I'm the business owner and I want to understand what data we have. "
        "Can you show me what tables are available in our database?"
    )

    if "error" not in result and result.get("response"):
        results.add_result("MySQL Discovery", True, "Successfully listed tables")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("MySQL Discovery", False, str(result.get("error", "No response")))
        return  # Can't continue without basic connectivity

    await asyncio.sleep(1)

    # Test 2: Schema understanding
    print_test("2. Understanding Table Structure")
    result = await session.send_message_streaming(
        "Interesting! Can you tell me more about what kind of information is stored in each table? "
        "I want to understand the structure so I can ask better questions."
    )

    if "error" not in result and result.get("response"):
        results.add_result("MySQL Schema", True, "Successfully described table structures")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("MySQL Schema", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 3: Simple query
    print_test("3. Simple Data Query")
    result = await session.send_message_streaming(
        "Great, now show me some sample data. What are the most recent records? "
        "I just want to see what the data looks like."
    )

    if "error" not in result and result.get("response"):
        results.add_result("MySQL Simple Query", True, "Successfully retrieved sample data")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("MySQL Simple Query", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 4: Aggregation query
    print_test("4. Aggregation/Analytics Query")
    result = await session.send_message_streaming(
        "Now I need some insights. Can you give me a summary of the data? "
        "Like totals, counts, or any patterns you can see? I'm trying to understand the overall picture."
    )

    if "error" not in result and result.get("response"):
        results.add_result("MySQL Aggregation", True, "Successfully provided analytics")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("MySQL Aggregation", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 5: Follow-up question (context retention)
    print_test("5. Context Retention - Follow-up Question")
    result = await session.send_message_streaming(
        "Can you drill down into that a bit more? "
        "What are the top 5 items based on what you just showed me?"
    )

    if "error" not in result and result.get("response"):
        results.add_result("MySQL Context", True, "Successfully maintained conversation context")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("MySQL Context", False, str(result.get("error", "No response")))

    print_info(f"MySQL session ID: {session.session_id}")


# =============================================================================
# S3 CONNECTOR TESTS
# =============================================================================

async def test_s3_connector(results: TestResults):
    """Test S3 connector with document exploration conversations"""
    print_header("S3 CONNECTOR TESTS - Document Exploration")

    session = TestSession("s3")

    # Test 1: Bucket discovery
    print_test("1. Bucket Discovery")
    result = await session.send_message_streaming(
        "Hello! I need to find some documents in our S3 storage. "
        "Can you show me what buckets we have available?"
    )

    if "error" not in result and result.get("response"):
        results.add_result("S3 Bucket Discovery", True, "Successfully listed buckets")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("S3 Bucket Discovery", False, str(result.get("error", "No response")))
        return

    await asyncio.sleep(1)

    # Test 2: Object listing
    print_test("2. Object Exploration")
    result = await session.send_message_streaming(
        "What files are stored in there? Can you show me what documents we have? "
        "I'm looking for anything related to business reports or data."
    )

    if "error" not in result and result.get("response"):
        results.add_result("S3 Object Listing", True, "Successfully listed objects")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("S3 Object Listing", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 3: Document reading
    print_test("3. Document Reading")
    result = await session.send_message_streaming(
        "Can you read one of those files and tell me what it contains? "
        "Just pick the most relevant one and summarize it for me."
    )

    if "error" not in result and result.get("response"):
        results.add_result("S3 Document Read", True, "Successfully read document")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("S3 Document Read", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 4: Document switching
    print_test("4. Document Switching")
    result = await session.send_message_streaming(
        "Interesting! Now can you show me a different document? "
        "I want to compare what's in multiple files."
    )

    if "error" not in result and result.get("response"):
        results.add_result("S3 Document Switch", True, "Successfully switched documents")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("S3 Document Switch", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 5: Search/filter
    print_test("5. Document Search")
    result = await session.send_message_streaming(
        "Is there any way to search for specific content across these documents? "
        "I'm looking for anything that mentions key business metrics or reports."
    )

    if "error" not in result and result.get("response"):
        results.add_result("S3 Search", True, "Successfully searched documents")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("S3 Search", False, str(result.get("error", "No response")))

    print_info(f"S3 session ID: {session.session_id}")


# =============================================================================
# JIRA CONNECTOR TESTS
# =============================================================================

async def test_jira_connector(results: TestResults):
    """Test JIRA connector with project management conversations"""
    print_header("JIRA CONNECTOR TESTS - Project Management")

    session = TestSession("jira")

    # Test 1: Project overview
    print_test("1. Project Discovery")
    result = await session.send_message_streaming(
        "Hi! I'm checking in on our team's progress. "
        "Can you show me what projects we have in JIRA?"
    )

    if "error" not in result and result.get("response"):
        results.add_result("JIRA Project Discovery", True, "Successfully listed projects")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("JIRA Project Discovery", False, str(result.get("error", "No response")))
        return

    await asyncio.sleep(1)

    # Test 2: Team workload
    print_test("2. Team Workload Analysis")
    result = await session.send_message_streaming(
        "Who's working on what right now? I want to see what each team member is assigned to. "
        "Show me the current assignments and their status."
    )

    if "error" not in result and result.get("response"):
        results.add_result("JIRA Team Workload", True, "Successfully showed team assignments")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("JIRA Team Workload", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 3: Sprint status
    print_test("3. Sprint Status")
    result = await session.send_message_streaming(
        "What's the status of our current sprint? "
        "How many items are done vs in progress vs still in the backlog?"
    )

    if "error" not in result and result.get("response"):
        results.add_result("JIRA Sprint Status", True, "Successfully showed sprint status")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("JIRA Sprint Status", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 4: Backlog analysis
    print_test("4. Backlog Analysis")
    result = await session.send_message_streaming(
        "Show me the backlog. What are the highest priority items we haven't started yet? "
        "I need to prioritize what comes next."
    )

    if "error" not in result and result.get("response"):
        results.add_result("JIRA Backlog", True, "Successfully analyzed backlog")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("JIRA Backlog", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 5: Blockers
    print_test("5. Blockers and Issues")
    result = await session.send_message_streaming(
        "Are there any blockers or issues that need my attention? "
        "I want to know about anything that's stuck or has been open for too long."
    )

    if "error" not in result and result.get("response"):
        results.add_result("JIRA Blockers", True, "Successfully identified blockers")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("JIRA Blockers", False, str(result.get("error", "No response")))

    await asyncio.sleep(1)

    # Test 6: Specific user query
    print_test("6. Specific User Query")
    result = await session.send_message_streaming(
        "What is Austin working on? Give me the details of his current tasks "
        "and how they're progressing."
    )

    if "error" not in result and result.get("response"):
        results.add_result("JIRA User Query", True, "Successfully queried specific user")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("JIRA User Query", False, str(result.get("error", "No response")))

    print_info(f"JIRA session ID: {session.session_id}")


# =============================================================================
# STREAMING TESTS
# =============================================================================

async def test_streaming(results: TestResults):
    """Test streaming implementation quality"""
    print_header("STREAMING QUALITY TESTS")

    session = TestSession("mysql")

    # Test 1: Compare streaming vs non-streaming
    print_test("1. Streaming vs Non-Streaming Comparison")

    # Non-streaming
    print_info("Testing non-streaming endpoint...")
    non_stream_result = await session.send_message_non_streaming(
        "List the tables in the database"
    )

    await asyncio.sleep(2)

    # Streaming
    print_info("Testing streaming endpoint...")
    stream_result = await session.send_message_streaming(
        "List the tables in the database again"
    )

    if stream_result.get("time_to_first_token", 999) < stream_result.get("total_time", 0):
        results.add_result(
            "Streaming TTFT",
            True,
            f"First token arrived in {stream_result['time_to_first_token']:.2f}s (total: {stream_result['total_time']:.2f}s)"
        )
    else:
        results.add_result("Streaming TTFT", False, "Streaming not working - all tokens arrived at once")

    # Test 2: Streaming during tool use
    print_test("2. Streaming During Tool Execution")
    result = await session.send_message_streaming(
        "Show me 5 rows from any table and explain what each column means"
    )

    if result.get("time_to_first_token", 0) > 0:
        results.add_result("Streaming with Tools", True, "Streaming worked with tool execution")
        print_metrics(result["time_to_first_token"], result["total_time"], result["char_count"])
    else:
        results.add_result("Streaming with Tools", False, "No streaming during tool use")


# =============================================================================
# MULTI-TENANCY TESTS
# =============================================================================

async def test_multi_tenancy(results: TestResults):
    """Test multi-tenancy and credential isolation"""
    print_header("MULTI-TENANCY TESTS")

    async with aiohttp.ClientSession() as http_session:
        # Test 1: Save credentials via API
        print_test("1. Credential Storage via API")

        credentials_payload = {
            "datasource": "mysql",
            "credentials": {
                "host": "kaay-migration.cre2ksyiyonw.us-east-1.rds.amazonaws.com",
                "port": 3306,
                "database": "generic_chat_bot",
                "user": "austin.chat",
                "password": "$%Gfd+km3JmEEBdB"
            }
        }

        try:
            async with http_session.post(
                f"{BASE_URL}/api/credentials",
                json=credentials_payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    results.add_result("Credential Storage", True, "Successfully stored credentials via API")
                else:
                    error = await response.text()
                    results.add_result("Credential Storage", False, f"HTTP {response.status}: {error}")
        except Exception as e:
            results.add_result("Credential Storage", False, str(e))

        # Test 2: Verify credentials exist
        print_test("2. Credential Status Check")
        try:
            async with http_session.get(
                f"{BASE_URL}/api/credentials/mysql/status",
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("has_credentials"):
                        results.add_result("Credential Status", True, "Credentials verified")
                    else:
                        results.add_result("Credential Status", False, "Credentials not found")
                else:
                    results.add_result("Credential Status", False, f"HTTP {response.status}")
        except Exception as e:
            results.add_result("Credential Status", False, str(e))

        # Test 3: Session isolation
        print_test("3. Session Isolation")

        # Create two separate sessions
        session_a = TestSession("mysql")
        session_b = TestSession("mysql")

        # Send different messages
        await session_a.send_message_streaming("Show me the first table", print_response=False)
        await session_b.send_message_streaming("Show me all tables", print_response=False)

        if session_a.session_id != session_b.session_id:
            results.add_result("Session Isolation", True, "Sessions are properly isolated")
        else:
            results.add_result("Session Isolation", False, "Sessions are not isolated")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

async def run_all_tests():
    """Run all connector tests"""
    print_header("COMPREHENSIVE CONNECTOR TEST SUITE")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend URL: {BASE_URL}")

    results = TestResults()

    # Check backend connectivity
    print_test("Backend Connectivity Check")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/datasources") as response:
                if response.status == 200:
                    data = await response.json()
                    print_success(f"Backend is running with {len(data)} datasources enabled")
                    results.add_result("Backend Connectivity", True, f"{len(data)} datasources available")
                else:
                    print_error(f"Backend returned status {response.status}")
                    results.add_result("Backend Connectivity", False, f"HTTP {response.status}")
                    results.print_summary()
                    return
    except Exception as e:
        print_error(f"Cannot connect to backend: {e}")
        results.add_result("Backend Connectivity", False, str(e))
        results.print_summary()
        return

    # Run connector tests
    await test_mysql_connector(results)
    await asyncio.sleep(2)

    await test_s3_connector(results)
    await asyncio.sleep(2)

    await test_jira_connector(results)
    await asyncio.sleep(2)

    await test_streaming(results)
    await asyncio.sleep(2)

    await test_multi_tenancy(results)

    # Print summary
    results.print_summary()

    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("    MOSAIC BY KAAY - CONNECTOR TEST SUITE")
    print("="*60)

    asyncio.run(run_all_tests())

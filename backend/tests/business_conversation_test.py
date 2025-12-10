#!/usr/bin/env python3
"""
Business Owner Conversational Test Suite

Simulates real conversations a business owner or executive would have
with the system - no technical jargon, just business questions.

Tests:
1. JIRA - Sprint reports, team status, blockers, deadlines, individual performance
2. S3 - Document discovery, content search, business intelligence from files
"""

import asyncio
import time
import aiohttp
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


async def send_message(session, datasource: str, message: str, session_id: str = None):
    """Send a message and get the full response with timing."""
    start = time.time()
    first_token_time = None
    full_response = ""

    url = f"{BASE_URL}/api/chat/message/stream"
    payload = {
        "message": message,
        "datasource": datasource,
    }
    if session_id:
        payload["session_id"] = session_id

    try:
        async with session.post(url, json=payload) as response:
            new_session_id = None
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    try:
                        data = json.loads(line_str[6:])
                        if data.get('type') == 'session':
                            new_session_id = data.get('session_id')
                        elif data.get('type') == 'content':
                            if first_token_time is None:
                                first_token_time = time.time() - start
                            full_response += data.get('content', '')
                    except:
                        pass

            total_time = time.time() - start
            ttft = first_token_time or total_time

            return {
                "response": full_response,
                "ttft": ttft,
                "total_time": total_time,
                "session_id": new_session_id or session_id,
                "success": len(full_response) > 0
            }
    except Exception as e:
        return {
            "response": f"Error: {e}",
            "ttft": 0,
            "total_time": 0,
            "session_id": session_id,
            "success": False
        }


def print_conversation(role: str, message: str, timing: dict = None):
    """Pretty print a conversation turn."""
    if role == "user":
        print(f"\n{BLUE}{BOLD}👤 Business Owner:{RESET}")
        print(f"   {message}")
    else:
        print(f"\n{GREEN}{BOLD}🤖 Mosaic:{RESET}")
        # Truncate long responses for readability
        if len(message) > 1500:
            print(f"   {message[:1500]}...")
            print(f"   {YELLOW}[Response truncated - {len(message)} total chars]{RESET}")
        else:
            print(f"   {message}")

        if timing:
            speed_color = GREEN if timing['ttft'] < 2 else YELLOW if timing['ttft'] < 5 else RED
            print(f"\n   {speed_color}⏱️  TTFT: {timing['ttft']:.2f}s | Total: {timing['total_time']:.2f}s{RESET}")


async def run_jira_business_tests():
    """Run JIRA tests simulating a business owner's questions."""
    print(f"\n{'='*70}")
    print(f"{CYAN}{BOLD}📊 JIRA BUSINESS CONVERSATION TEST{RESET}")
    print(f"{CYAN}Simulating: CEO/Business Owner checking on project status{RESET}")
    print(f"{'='*70}")

    conversations = [
        # Conversation 1: High-level overview
        {
            "name": "Executive Overview",
            "questions": [
                "What projects are we currently working on?",
                "Which project has the most activity right now?",
                "Are there any projects that seem stalled or have issues?",
            ]
        },
        # Conversation 2: Team workload
        {
            "name": "Team Performance Review",
            "questions": [
                "Who's working on what right now?",
                "Who has the most tasks assigned to them?",
                "Are there any team members who seem overloaded?",
            ]
        },
        # Conversation 3: Sprint status
        {
            "name": "Sprint Health Check",
            "questions": [
                "What's the status of our current sprint?",
                "How many tasks are completed vs still in progress?",
                "What's blocking us from finishing the sprint?",
            ]
        },
        # Conversation 4: Specific person check
        {
            "name": "Individual Status Check",
            "questions": [
                "What is Dinesh working on?",
                "Show me all open issues assigned to the team",
                "Which tasks have been stuck the longest?",
            ]
        },
        # Conversation 5: Blockers and risks
        {
            "name": "Risk Assessment",
            "questions": [
                "What are our current blockers?",
                "Are there any high priority bugs we need to worry about?",
                "What tasks are overdue or at risk?",
            ]
        },
    ]

    results = []

    async with aiohttp.ClientSession() as http_session:
        for conv in conversations:
            print(f"\n{YELLOW}{BOLD}📌 Conversation: {conv['name']}{RESET}")
            print(f"{'-'*50}")

            session_id = None
            conv_results = []

            for question in conv['questions']:
                print_conversation("user", question)

                result = await send_message(http_session, "jira", question, session_id)
                session_id = result['session_id']

                print_conversation("assistant", result['response'], {
                    'ttft': result['ttft'],
                    'total_time': result['total_time']
                })

                conv_results.append({
                    "question": question,
                    "ttft": result['ttft'],
                    "total_time": result['total_time'],
                    "success": result['success'],
                    "response_length": len(result['response'])
                })

                # Small delay between questions
                await asyncio.sleep(0.5)

            results.extend(conv_results)

    return results


async def run_s3_business_tests():
    """Run S3 tests simulating a business owner exploring documents."""
    print(f"\n{'='*70}")
    print(f"{CYAN}{BOLD}📁 S3 DOCUMENT INTELLIGENCE TEST{RESET}")
    print(f"{CYAN}Simulating: Business Owner exploring company documents{RESET}")
    print(f"{'='*70}")

    conversations = [
        # Conversation 1: Document discovery
        {
            "name": "Document Discovery",
            "questions": [
                "What storage buckets do we have?",
                "What documents are stored in our main bucket?",
                "Can you categorize the types of documents we have?",
            ]
        },
        # Conversation 2: Content exploration
        {
            "name": "Architecture Review",
            "questions": [
                "Show me any architecture documentation we have",
                "What does our chatbot architecture look like?",
                "Are there any technical specifications I should know about?",
            ]
        },
        # Conversation 3: Business documents
        {
            "name": "Business Intelligence",
            "questions": [
                "Do we have any executive summaries or business documents?",
                "What's in the PC Platform documentation?",
                "Search for any documents about our platform strategy",
            ]
        },
    ]

    results = []

    async with aiohttp.ClientSession() as http_session:
        for conv in conversations:
            print(f"\n{YELLOW}{BOLD}📌 Conversation: {conv['name']}{RESET}")
            print(f"{'-'*50}")

            session_id = None
            conv_results = []

            for question in conv['questions']:
                print_conversation("user", question)

                result = await send_message(http_session, "s3", question, session_id)
                session_id = result['session_id']

                print_conversation("assistant", result['response'], {
                    'ttft': result['ttft'],
                    'total_time': result['total_time']
                })

                conv_results.append({
                    "question": question,
                    "ttft": result['ttft'],
                    "total_time": result['total_time'],
                    "success": result['success'],
                    "response_length": len(result['response'])
                })

                # Small delay between questions
                await asyncio.sleep(0.5)

            results.extend(conv_results)

    return results


def print_summary(jira_results: list, s3_results: list):
    """Print a summary of all test results."""
    print(f"\n{'='*70}")
    print(f"{BOLD}📈 TEST SUMMARY REPORT{RESET}")
    print(f"{'='*70}")

    all_results = jira_results + s3_results

    # Calculate statistics
    total_tests = len(all_results)
    passed = sum(1 for r in all_results if r['success'])
    avg_ttft = sum(r['ttft'] for r in all_results) / len(all_results) if all_results else 0
    avg_total = sum(r['total_time'] for r in all_results) / len(all_results) if all_results else 0

    fast_responses = sum(1 for r in all_results if r['ttft'] < 2)
    medium_responses = sum(1 for r in all_results if 2 <= r['ttft'] < 5)
    slow_responses = sum(1 for r in all_results if r['ttft'] >= 5)

    print(f"\n{BOLD}Overall Statistics:{RESET}")
    print(f"  Total Queries: {total_tests}")
    print(f"  Successful: {GREEN}{passed}/{total_tests}{RESET}")
    print(f"  Average TTFT: {avg_ttft:.2f}s")
    print(f"  Average Total Time: {avg_total:.2f}s")

    print(f"\n{BOLD}Response Speed Distribution:{RESET}")
    print(f"  {GREEN}⚡ Fast (<2s):{RESET} {fast_responses} queries")
    print(f"  {YELLOW}⏱️  Medium (2-5s):{RESET} {medium_responses} queries")
    print(f"  {RED}🐢 Slow (>5s):{RESET} {slow_responses} queries")

    # JIRA specific
    if jira_results:
        jira_avg = sum(r['ttft'] for r in jira_results) / len(jira_results)
        print(f"\n{BOLD}JIRA Performance:{RESET}")
        print(f"  Queries: {len(jira_results)}")
        print(f"  Average TTFT: {jira_avg:.2f}s")

    # S3 specific
    if s3_results:
        s3_avg = sum(r['ttft'] for r in s3_results) / len(s3_results)
        print(f"\n{BOLD}S3 Performance:{RESET}")
        print(f"  Queries: {len(s3_results)}")
        print(f"  Average TTFT: {s3_avg:.2f}s")

    # Performance rating
    print(f"\n{BOLD}🎯 Overall Performance Rating:{RESET}")
    if avg_ttft < 2:
        print(f"  {GREEN}⚡⚡⚡ EXCELLENT - Business-ready performance!{RESET}")
    elif avg_ttft < 4:
        print(f"  {GREEN}⚡⚡ GOOD - Acceptable for business use{RESET}")
    elif avg_ttft < 6:
        print(f"  {YELLOW}⚡ ACCEPTABLE - Some optimization needed{RESET}")
    else:
        print(f"  {RED}⚠️  NEEDS IMPROVEMENT - Too slow for business use{RESET}")

    # Detailed breakdown table
    print(f"\n{BOLD}Detailed Query Performance:{RESET}")
    print(f"{'Query':<50} {'TTFT':<10} {'Status':<10}")
    print(f"{'-'*70}")

    for r in all_results:
        question = r['question'][:47] + "..." if len(r['question']) > 50 else r['question']
        ttft = f"{r['ttft']:.2f}s"
        status = f"{GREEN}✓{RESET}" if r['success'] else f"{RED}✗{RESET}"
        speed = f"{GREEN}" if r['ttft'] < 2 else f"{YELLOW}" if r['ttft'] < 5 else f"{RED}"
        print(f"{question:<50} {speed}{ttft:<10}{RESET} {status}")

    print(f"\n{'='*70}")
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")


async def main():
    """Run all business conversation tests."""
    print(f"\n{BOLD}{'='*70}")
    print(f"🚀 MOSAIC BUSINESS CONVERSATION TEST SUITE")
    print(f"{'='*70}{RESET}")
    print(f"\nThis test simulates real business conversations with the system.")
    print(f"Questions are designed for CEOs, Product Managers, and Business Owners.")
    print(f"Focus: Speed, Accuracy, and Business Value\n")

    # Run JIRA tests
    jira_results = await run_jira_business_tests()

    # Run S3 tests
    s3_results = await run_s3_business_tests()

    # Print summary
    print_summary(jira_results, s3_results)


if __name__ == "__main__":
    asyncio.run(main())

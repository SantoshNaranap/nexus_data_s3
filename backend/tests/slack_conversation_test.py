#!/usr/bin/env python3
"""
Slack Conversational Ability Test Suite

Tests complex, real-world Slack queries that users would actually ask:
- Summarizing missed messages across DMs and channels
- Finding specific conversations with people
- Searching for content across the workspace
- Understanding context and follow-up questions

This validates the system's ability to:
1. Route to correct tools (read_dm_with_user, search_messages, list_channels, etc.)
2. Handle natural language variations
3. Maintain conversation context
4. Synthesize results into useful summaries
"""

import asyncio
import time
import aiohttp
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 120  # 2 minute timeout for complex queries

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


class SlackConversationTester:
    """Test suite for Slack conversational abilities."""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.session_id: Optional[str] = None
    
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
        thinking_content = ""
        tools_used = []
        sources = []
        
        url = f"{BASE_URL}/api/chat/message/stream"
        payload = {
            "message": message,
            "datasource": "slack",
        }
        
        # Use existing session for context, or start new
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
                            elif event_type == 'thinking':
                                thinking_content += data.get('content', '')
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
                    "thinking": thinking_content,
                    "tools_used": tools_used,
                    "sources": sources,
                    "ttft": first_token_time or total_time,
                    "total_time": total_time,
                    "success": len(full_response) > 50,  # Meaningful response
                    "error": None
                }
                
        except asyncio.TimeoutError:
            return {
                "response": "",
                "thinking": "",
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
                "thinking": "",
                "tools_used": [],
                "sources": [],
                "ttft": 0,
                "total_time": time.time() - start,
                "success": False,
                "error": str(e)
            }
    
    def print_result(self, query: str, result: Dict[str, Any], expected_tools: List[str] = None):
        """Pretty print a test result."""
        print(f"\n{BLUE}{BOLD}👤 User Query:{RESET}")
        print(f"   \"{query}\"")
        
        # Show tools used
        if result['tools_used']:
            print(f"\n{MAGENTA}   🔧 Tools invoked: {', '.join(result['tools_used'])}{RESET}")
        
        # Check if expected tools were used
        if expected_tools:
            used_set = set(t.lower() for t in result['tools_used'])
            expected_set = set(t.lower() for t in expected_tools)
            # Check if any expected tool appears in any used tool name
            matched = any(
                any(exp in used for used in str(result['tools_used']).lower().split())
                for exp in expected_set
            )
            if matched:
                print(f"   {GREEN}✓ Correct tool routing{RESET}")
            else:
                print(f"   {RED}✗ Expected tools: {expected_tools}{RESET}")
        
        # Show response
        print(f"\n{GREEN}{BOLD}🤖 Mosaic Response:{RESET}")
        response = result['response']
        if len(response) > 2000:
            print(f"   {response[:2000]}...")
            print(f"   {DIM}[Truncated - {len(response)} total chars]{RESET}")
        else:
            print(f"   {response}")
        
        # Show timing
        speed_color = GREEN if result['ttft'] < 3 else YELLOW if result['ttft'] < 6 else RED
        print(f"\n   {speed_color}⏱️  TTFT: {result['ttft']:.2f}s | Total: {result['total_time']:.2f}s{RESET}")
        
        if result['error']:
            print(f"   {RED}❌ Error: {result['error']}{RESET}")
        
        return result['success']


async def test_message_summary_queries(tester: SlackConversationTester, session: aiohttp.ClientSession):
    """Test complex message summarization queries."""
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}📬 TEST 1: MESSAGE SUMMARIZATION QUERIES{RESET}")
    print(f"{CYAN}Testing: Can the system summarize messages across DMs and channels?{RESET}")
    print(f"{'='*80}")
    
    test_cases = [
        {
            "query": "I missed all messages from yesterday, can you summarize what I have received across DMs and groups?",
            "expected_tools": ["search", "read_dm", "list"],
            "description": "Complex multi-source summary"
        },
        {
            "query": "What did I miss today? Give me a quick summary of all important messages",
            "expected_tools": ["search", "read"],
            "description": "Daily summary request"
        },
        {
            "query": "Summarize all the DMs I received this week",
            "expected_tools": ["list_dms", "read_dm"],
            "description": "DM-focused summary"
        },
        {
            "query": "What's happening in my team channels? Any important updates?",
            "expected_tools": ["list_channels", "read", "search"],
            "description": "Channel updates summary"
        },
    ]
    
    results = []
    for tc in test_cases:
        print(f"\n{YELLOW}📌 {tc['description']}{RESET}")
        result = await tester.send_message(session, tc["query"], new_conversation=True)
        success = tester.print_result(tc["query"], result, tc["expected_tools"])
        results.append({
            "test": tc["description"],
            "query": tc["query"],
            "success": success,
            **result
        })
        await asyncio.sleep(1)  # Rate limiting
    
    return results


async def test_person_specific_queries(tester: SlackConversationTester, session: aiohttp.ClientSession):
    """Test queries about specific people."""
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}👥 TEST 2: PERSON-SPECIFIC QUERIES{RESET}")
    print(f"{CYAN}Testing: Can the system find and summarize messages from/to specific people?{RESET}")
    print(f"{'='*80}")
    
    test_cases = [
        {
            "query": "What did Ananth say to me recently?",
            "expected_tools": ["read_dm_with_user"],
            "description": "Read DM with specific person"
        },
        {
            "query": "Show me my conversation with Akash",
            "expected_tools": ["read_dm_with_user"],
            "description": "View DM conversation"
        },
        {
            "query": "Did anyone message me about the project?",
            "expected_tools": ["search", "read_dm"],
            "description": "Topic-based message search"
        },
        {
            "query": "What messages has Austin sent in the last few days?",
            "expected_tools": ["read_dm_with_user", "search"],
            "description": "Recent messages from person"
        },
        {
            "query": "Find all mentions of my name in channels",
            "expected_tools": ["search"],
            "description": "Self-mention search"
        },
    ]
    
    results = []
    for tc in test_cases:
        print(f"\n{YELLOW}📌 {tc['description']}{RESET}")
        result = await tester.send_message(session, tc["query"], new_conversation=True)
        success = tester.print_result(tc["query"], result, tc["expected_tools"])
        results.append({
            "test": tc["description"],
            "query": tc["query"],
            "success": success,
            **result
        })
        await asyncio.sleep(1)
    
    return results


async def test_content_search_queries(tester: SlackConversationTester, session: aiohttp.ClientSession):
    """Test content search and discovery queries."""
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}🔍 TEST 3: CONTENT SEARCH QUERIES{RESET}")
    print(f"{CYAN}Testing: Can the system find specific content, credentials, and information?{RESET}")
    print(f"{'='*80}")
    
    test_cases = [
        {
            "query": "Search for any messages containing API keys or credentials",
            "expected_tools": ["search_messages"],
            "description": "Credential search"
        },
        {
            "query": "Find discussions about the database migration",
            "expected_tools": ["search_messages"],
            "description": "Topic search"
        },
        {
            "query": "Look for any messages with links to documents",
            "expected_tools": ["search_messages"],
            "description": "Link/document search"
        },
        {
            "query": "What bugs or issues have been discussed recently?",
            "expected_tools": ["search_messages"],
            "description": "Bug discussion search"
        },
    ]
    
    results = []
    for tc in test_cases:
        print(f"\n{YELLOW}📌 {tc['description']}{RESET}")
        result = await tester.send_message(session, tc["query"], new_conversation=True)
        success = tester.print_result(tc["query"], result, tc["expected_tools"])
        results.append({
            "test": tc["description"],
            "query": tc["query"],
            "success": success,
            **result
        })
        await asyncio.sleep(1)
    
    return results


async def test_workspace_discovery_queries(tester: SlackConversationTester, session: aiohttp.ClientSession):
    """Test workspace navigation and discovery queries."""
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}🏢 TEST 4: WORKSPACE DISCOVERY{RESET}")
    print(f"{CYAN}Testing: Can the system navigate and list workspace resources?{RESET}")
    print(f"{'='*80}")
    
    test_cases = [
        {
            "query": "What channels do we have?",
            "expected_tools": ["list_channels"],
            "description": "List all channels"
        },
        {
            "query": "Who are the people in this workspace?",
            "expected_tools": ["list_users"],
            "description": "List workspace members"
        },
        {
            "query": "Show me my direct message conversations",
            "expected_tools": ["list_dms"],
            "description": "List DM conversations"
        },
        {
            "query": "What private channels am I part of?",
            "expected_tools": ["list_channels"],
            "description": "List private channels"
        },
    ]
    
    results = []
    for tc in test_cases:
        print(f"\n{YELLOW}📌 {tc['description']}{RESET}")
        result = await tester.send_message(session, tc["query"], new_conversation=True)
        success = tester.print_result(tc["query"], result, tc["expected_tools"])
        results.append({
            "test": tc["description"],
            "query": tc["query"],
            "success": success,
            **result
        })
        await asyncio.sleep(1)
    
    return results


async def test_multi_turn_conversation(tester: SlackConversationTester, session: aiohttp.ClientSession):
    """Test multi-turn conversations with context."""
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}💬 TEST 5: MULTI-TURN CONVERSATION{RESET}")
    print(f"{CYAN}Testing: Can the system maintain context across multiple messages?{RESET}")
    print(f"{'='*80}")
    
    # This should be a single conversation with follow-ups
    conversation = [
        {
            "query": "Who are the people I have DMs with?",
            "expected_tools": ["list_dms", "list_users"],
            "description": "Initial context - list DMs"
        },
        {
            "query": "Show me the messages from the first person you mentioned",
            "expected_tools": ["read_dm"],
            "description": "Follow-up - uses context from previous response"
        },
        {
            "query": "Can you summarize what they were talking about?",
            "expected_tools": [],  # No tool needed - summarize previous result
            "description": "Follow-up - summarize without new tool call"
        },
    ]
    
    results = []
    
    # Start fresh conversation
    tester.session_id = None
    
    for i, tc in enumerate(conversation):
        print(f"\n{YELLOW}📌 Turn {i+1}: {tc['description']}{RESET}")
        # Use same session for context
        result = await tester.send_message(session, tc["query"], new_conversation=(i == 0))
        success = tester.print_result(tc["query"], result, tc["expected_tools"])
        results.append({
            "test": tc["description"],
            "query": tc["query"],
            "turn": i + 1,
            "success": success,
            **result
        })
        await asyncio.sleep(1)
    
    return results


async def test_natural_language_variations(tester: SlackConversationTester, session: aiohttp.ClientSession):
    """Test that different phrasings route to correct tools."""
    print(f"\n{'='*80}")
    print(f"{CYAN}{BOLD}🗣️ TEST 6: NATURAL LANGUAGE VARIATIONS{RESET}")
    print(f"{CYAN}Testing: Do different phrasings of the same intent work correctly?{RESET}")
    print(f"{'='*80}")
    
    # All these should use read_dm_with_user
    dm_variations = [
        "What did John say?",
        "Show me messages from John",
        "John's messages please",
        "Did John send me anything?",
        "Check my DM with John",
        "Conversations with John",
        "John and I chatted about what?",
    ]
    
    print(f"\n{YELLOW}📌 Testing DM query variations (all should use read_dm_with_user){RESET}")
    
    results = []
    for query in dm_variations:
        result = await tester.send_message(session, query, new_conversation=True)
        
        # Check if read_dm was used
        tools_str = str(result['tools_used']).lower()
        used_dm_tool = 'read_dm' in tools_str or 'dm' in tools_str
        
        status = f"{GREEN}✓{RESET}" if used_dm_tool else f"{RED}✗{RESET}"
        timing_color = GREEN if result['ttft'] < 3 else YELLOW
        
        print(f"   {status} \"{query}\" - {timing_color}{result['ttft']:.2f}s{RESET}")
        if not used_dm_tool and result['tools_used']:
            print(f"      {DIM}Used: {result['tools_used']}{RESET}")
        
        results.append({
            "query": query,
            "correct_routing": used_dm_tool,
            "tools_used": result['tools_used'],
            **result
        })
        await asyncio.sleep(0.5)
    
    return results


def print_summary(all_results: List[Dict[str, Any]]):
    """Print comprehensive test summary."""
    print(f"\n{'='*80}")
    print(f"{BOLD}📊 COMPREHENSIVE TEST SUMMARY{RESET}")
    print(f"{'='*80}")
    
    # Flatten all results
    flat_results = []
    for results in all_results:
        if isinstance(results, list):
            flat_results.extend(results)
        else:
            flat_results.append(results)
    
    total = len(flat_results)
    successful = sum(1 for r in flat_results if r.get('success', False))
    
    # Timing stats
    times = [r['ttft'] for r in flat_results if r.get('ttft', 0) > 0]
    avg_ttft = sum(times) / len(times) if times else 0
    max_ttft = max(times) if times else 0
    min_ttft = min(times) if times else 0
    
    fast = sum(1 for t in times if t < 3)
    medium = sum(1 for t in times if 3 <= t < 6)
    slow = sum(1 for t in times if t >= 6)
    
    print(f"\n{BOLD}Overall Results:{RESET}")
    print(f"  Total Tests: {total}")
    print(f"  Successful: {GREEN}{successful}/{total} ({100*successful/total:.1f}%){RESET}")
    
    print(f"\n{BOLD}Timing Performance:{RESET}")
    print(f"  Average TTFT: {avg_ttft:.2f}s")
    print(f"  Fastest: {min_ttft:.2f}s")
    print(f"  Slowest: {max_ttft:.2f}s")
    
    print(f"\n{BOLD}Speed Distribution:{RESET}")
    print(f"  {GREEN}⚡ Fast (<3s):{RESET} {fast} tests")
    print(f"  {YELLOW}⏱️  Medium (3-6s):{RESET} {medium} tests")
    print(f"  {RED}🐢 Slow (>6s):{RESET} {slow} tests")
    
    # Tool routing accuracy
    routing_tests = [r for r in flat_results if 'correct_routing' in r]
    if routing_tests:
        correct_routing = sum(1 for r in routing_tests if r['correct_routing'])
        print(f"\n{BOLD}Tool Routing Accuracy:{RESET}")
        print(f"  Correct: {GREEN}{correct_routing}/{len(routing_tests)} ({100*correct_routing/len(routing_tests):.1f}%){RESET}")
    
    # Overall rating
    print(f"\n{BOLD}🎯 Overall Conversational Ability Rating:{RESET}")
    success_rate = successful / total if total > 0 else 0
    
    if success_rate >= 0.9 and avg_ttft < 3:
        print(f"  {GREEN}⭐⭐⭐⭐⭐ EXCELLENT - Production ready!{RESET}")
    elif success_rate >= 0.8 and avg_ttft < 5:
        print(f"  {GREEN}⭐⭐⭐⭐ GOOD - Minor improvements needed{RESET}")
    elif success_rate >= 0.6 and avg_ttft < 8:
        print(f"  {YELLOW}⭐⭐⭐ ACCEPTABLE - Needs optimization{RESET}")
    elif success_rate >= 0.4:
        print(f"  {YELLOW}⭐⭐ NEEDS WORK - Significant issues{RESET}")
    else:
        print(f"  {RED}⭐ CRITICAL - Major issues to address{RESET}")
    
    # Failed tests
    failed = [r for r in flat_results if not r.get('success', False)]
    if failed:
        print(f"\n{RED}{BOLD}Failed Tests:{RESET}")
        for f in failed[:5]:  # Show first 5 failures
            print(f"  ✗ {f.get('query', f.get('test', 'Unknown'))[:60]}...")
            if f.get('error'):
                print(f"    Error: {f['error']}")
    
    print(f"\n{'='*80}")
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")


async def main():
    """Run all Slack conversational tests."""
    print(f"\n{BOLD}{'='*80}")
    print(f"🎯 SLACK CONVERSATIONAL ABILITY TEST SUITE")
    print(f"{'='*80}{RESET}")
    print(f"\nThis test validates Mosaic's ability to understand and respond to")
    print(f"complex, natural language queries about Slack messages and workspace.")
    print(f"\n{YELLOW}⚠️  Ensure the backend is running and Slack credentials are configured.{RESET}\n")
    
    tester = SlackConversationTester()
    all_results = []
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Message summarization
        results = await test_message_summary_queries(tester, session)
        all_results.append(results)
        
        # Test 2: Person-specific queries  
        results = await test_person_specific_queries(tester, session)
        all_results.append(results)
        
        # Test 3: Content search
        results = await test_content_search_queries(tester, session)
        all_results.append(results)
        
        # Test 4: Workspace discovery
        results = await test_workspace_discovery_queries(tester, session)
        all_results.append(results)
        
        # Test 5: Multi-turn conversation
        results = await test_multi_turn_conversation(tester, session)
        all_results.append(results)
        
        # Test 6: Natural language variations
        results = await test_natural_language_variations(tester, session)
        all_results.append(results)
    
    # Print summary
    print_summary(all_results)


if __name__ == "__main__":
    asyncio.run(main())




#!/usr/bin/env python3
"""
Comprehensive Test Suite for ConnectorMCP
Tests all connectors with various query scenarios.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any
import httpx

BASE_URL = "http://localhost:8000"

# Test results storage
test_results = {
    "start_time": None,
    "end_time": None,
    "total_tests": 0,
    "passed": 0,
    "failed": 0,
    "warnings": 0,
    "tests": [],
    "discovered_data": {},
}


async def send_chat_message(datasource: str, message: str, timeout: float = 60.0) -> dict:
    """Send a chat message and get response."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/api/chat/message",
                json={
                    "message": message,
                    "datasource": datasource,
                },
            )
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}: {response.text}"}
            return response.json()
        except Exception as e:
            return {"error": str(e)}


def evaluate_response(response: dict, test_case: dict) -> dict:
    """Evaluate if response meets test criteria."""
    result = {
        "test_name": test_case["name"],
        "datasource": test_case["datasource"],
        "query": test_case["query"],
        "status": "UNKNOWN",
        "response_preview": "",
        "issues": [],
        "duration_ms": 0,
    }

    if "error" in response:
        result["status"] = "FAILED"
        result["issues"].append(f"Request error: {response['error']}")
        return result

    content = response.get("response", "")
    result["response_preview"] = content[:500] + "..." if len(content) > 500 else content

    # Check for hallucination indicators
    hallucination_phrases = [
        "I don't have access",
        "I cannot",
        "I'm unable",
        "error occurred",
        "failed to",
    ]

    # Check for empty/no data responses when data was expected
    no_data_phrases = [
        "no results found",
        "no activity found",
        "no data",
        "couldn't find",
        "not found",
        "0 results",
        "no issues",
        "no messages",
    ]

    # Check expected conditions
    issues = []

    if test_case.get("expect_data", True):
        # Should have some data
        if any(phrase in content.lower() for phrase in no_data_phrases):
            if test_case.get("allow_no_data", False):
                result["status"] = "WARNING"
                issues.append("No data found (may be expected)")
            else:
                result["status"] = "WARNING"
                issues.append("Query returned no data - verify if expected")

    if test_case.get("expect_person_found", False):
        # Should find the person
        person = test_case.get("person", "")
        if f"not found" in content.lower() and person.lower() in content.lower():
            result["status"] = "FAILED"
            issues.append(f"Person '{person}' was not found")

    if test_case.get("expect_error", False):
        # Should return an error
        if not any(phrase in content.lower() for phrase in ["error", "not found", "invalid"]):
            result["status"] = "WARNING"
            issues.append("Expected error but got a response")

    if test_case.get("expect_sources", False):
        # Should have sources section
        if "sources:" not in content.lower() and "source:" not in content.lower():
            issues.append("Missing Sources section at end of response")

    if test_case.get("expect_ambiguous", False):
        # Should indicate ambiguity
        if "ambiguous" not in content.lower() and "multiple" not in content.lower() and "which" not in content.lower():
            result["status"] = "WARNING"
            issues.append("Expected ambiguity indication but none found")

    # Check for specific content
    if test_case.get("must_contain"):
        for term in test_case["must_contain"]:
            if term.lower() not in content.lower():
                issues.append(f"Missing expected content: '{term}'")

    if test_case.get("must_not_contain"):
        for term in test_case["must_not_contain"]:
            if term.lower() in content.lower():
                issues.append(f"Contains unexpected content: '{term}'")

    # Set final status
    if not issues:
        result["status"] = "PASSED"
    elif result["status"] == "UNKNOWN":
        result["status"] = "WARNING" if len(issues) == 1 else "FAILED"

    result["issues"] = issues
    return result


async def discover_slack_users() -> list:
    """Discover all users in Slack workspace."""
    print("  Discovering Slack users...")
    response = await send_chat_message("slack", "List all users in the workspace")

    # Parse users from response
    users = []
    content = response.get("response", "")

    # Try to extract names from the response
    lines = content.split("\n")
    for line in lines:
        # Look for patterns like "Name" or "@name" or "- Name"
        if "|" in line and "@" not in line[:5]:  # Table row
            parts = [p.strip() for p in line.split("|")]
            for part in parts:
                if part and len(part) > 2 and not part.startswith("-") and part not in ["Name", "Status", "Email", "Title"]:
                    users.append(part)

    # Dedupe
    users = list(set(users))[:20]  # Limit to 20 for testing
    return users


async def discover_jira_data() -> dict:
    """Discover JIRA projects and assignees."""
    print("  Discovering JIRA projects...")

    data = {"projects": [], "assignees": []}

    # Get projects
    response = await send_chat_message("jira", "List all JIRA projects")
    content = response.get("response", "")

    # Extract project keys
    import re
    project_keys = re.findall(r'\b([A-Z]{2,10})\b', content)
    data["projects"] = list(set(project_keys))[:10]

    # Get assignees from a sample query
    response = await send_chat_message("jira", "Show me all open issues with assignees")
    content = response.get("response", "")

    # Extract names (rough heuristic)
    lines = content.split("\n")
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            for part in parts:
                if part and " " in part and len(part) > 5 and len(part) < 30:
                    # Likely a name
                    if not any(c.isdigit() for c in part) and not part.startswith("-"):
                        data["assignees"].append(part)

    data["assignees"] = list(set(data["assignees"]))[:10]
    return data


async def run_test(test_case: dict) -> dict:
    """Run a single test case."""
    print(f"  Running: {test_case['name']}")

    start = time.time()
    response = await send_chat_message(
        test_case["datasource"],
        test_case["query"],
        timeout=test_case.get("timeout", 60.0)
    )
    duration = (time.time() - start) * 1000

    result = evaluate_response(response, test_case)
    result["duration_ms"] = round(duration)

    # Print status
    status_icon = {"PASSED": "✓", "FAILED": "✗", "WARNING": "⚠"}.get(result["status"], "?")
    print(f"    {status_icon} {result['status']} ({result['duration_ms']}ms)")
    if result["issues"]:
        for issue in result["issues"]:
            print(f"      - {issue}")

    return result


async def run_comprehensive_tests():
    """Run all comprehensive tests."""
    global test_results

    test_results["start_time"] = datetime.now().isoformat()

    print("\n" + "=" * 70)
    print("COMPREHENSIVE TEST SUITE - ConnectorMCP")
    print("=" * 70)

    # Phase 1: Discovery
    print("\n[PHASE 1] Data Discovery")
    print("-" * 40)

    slack_users = await discover_slack_users()
    test_results["discovered_data"]["slack_users"] = slack_users
    print(f"  Found {len(slack_users)} Slack users")

    jira_data = await discover_jira_data()
    test_results["discovered_data"]["jira_projects"] = jira_data["projects"]
    test_results["discovered_data"]["jira_assignees"] = jira_data["assignees"]
    print(f"  Found {len(jira_data['projects'])} JIRA projects")
    print(f"  Found {len(jira_data['assignees'])} JIRA assignees")

    # Phase 2: Build Test Cases
    print("\n[PHASE 2] Building Test Cases")
    print("-" * 40)

    test_cases = []

    # ========== SLACK TESTS ==========

    # Test: Person queries for discovered users
    for user in slack_users[:5]:  # Test first 5 users
        test_cases.append({
            "name": f"Slack: Activity for {user}",
            "datasource": "slack",
            "query": f"What is {user} working on?",
            "expect_data": True,
            "expect_person_found": True,
            "person": user,
            "expect_sources": True,
            "allow_no_data": True,  # They might have no recent activity
        })

    # Test: Various question formats about a person
    if slack_users:
        test_person = slack_users[0]
        test_cases.extend([
            {
                "name": f"Slack: DM history with {test_person}",
                "datasource": "slack",
                "query": f"What did {test_person} last say to me?",
                "expect_data": True,
                "allow_no_data": True,
            },
            {
                "name": f"Slack: Online status for {test_person}",
                "datasource": "slack",
                "query": f"Is {test_person} online?",
                "expect_data": True,
            },
            {
                "name": f"Slack: Recent messages from {test_person}",
                "datasource": "slack",
                "query": f"Show me recent messages from {test_person}",
                "expect_data": True,
                "allow_no_data": True,
            },
        ])

    # Test: Non-existent person (should return not found)
    test_cases.append({
        "name": "Slack: Non-existent person",
        "datasource": "slack",
        "query": "What is Zyxwvutsrq McFakename working on?",
        "expect_error": True,
        "must_contain": ["not found"],
    })

    # Test: Channel queries
    test_cases.extend([
        {
            "name": "Slack: List channels",
            "datasource": "slack",
            "query": "What channels are available?",
            "expect_data": True,
        },
        {
            "name": "Slack: Read general channel",
            "datasource": "slack",
            "query": "Show me recent messages in #general",
            "expect_data": True,
            "allow_no_data": True,
        },
        {
            "name": "Slack: Search for keyword",
            "datasource": "slack",
            "query": "Search for messages about deployment",
            "expect_data": True,
            "allow_no_data": True,
        },
    ])

    # Test: Ambiguous name (common first name)
    test_cases.append({
        "name": "Slack: Potentially ambiguous name",
        "datasource": "slack",
        "query": "What is John working on?",
        "expect_data": True,
        "allow_no_data": True,
    })

    # ========== JIRA TESTS ==========

    # Test: Project queries
    for project in jira_data["projects"][:3]:
        test_cases.append({
            "name": f"JIRA: Issues in {project}",
            "datasource": "jira",
            "query": f"Show me open issues in {project}",
            "expect_data": True,
            "expect_sources": True,
            "allow_no_data": True,
        })

    # Test: Person queries in JIRA
    for assignee in jira_data["assignees"][:3]:
        first_name = assignee.split()[0] if " " in assignee else assignee
        test_cases.append({
            "name": f"JIRA: Work for {first_name}",
            "datasource": "jira",
            "query": f"What is {first_name} working on?",
            "expect_data": True,
            "expect_person_found": True,
            "person": first_name,
            "expect_sources": True,
            "allow_no_data": True,
        })

    # Test: Analytical queries
    test_cases.extend([
        {
            "name": "JIRA: Projects behind schedule",
            "datasource": "jira",
            "query": "What projects are behind schedule?",
            "expect_data": True,
            "allow_no_data": True,
            "must_not_contain": ["list of projects", "here are all projects"],
        },
        {
            "name": "JIRA: Overdue issues",
            "datasource": "jira",
            "query": "Show me overdue issues",
            "expect_data": True,
            "allow_no_data": True,
        },
        {
            "name": "JIRA: Blocked issues",
            "datasource": "jira",
            "query": "What issues are blocked?",
            "expect_data": True,
            "allow_no_data": True,
        },
        {
            "name": "JIRA: Bug count",
            "datasource": "jira",
            "query": "How many open bugs are there?",
            "expect_data": True,
        },
        {
            "name": "JIRA: In review issues",
            "datasource": "jira",
            "query": "What's in code review?",
            "expect_data": True,
            "allow_no_data": True,
        },
    ])

    # Test: Non-existent person in JIRA
    test_cases.append({
        "name": "JIRA: Non-existent person",
        "datasource": "jira",
        "query": "What is Fakeperson Notreal working on?",
        "expect_error": True,
        "must_contain": ["not found"],
    })

    # Test: Context maintenance (follow-up)
    if jira_data["projects"]:
        project = jira_data["projects"][0]
        test_cases.append({
            "name": f"JIRA: Context - initial query for {project}",
            "datasource": "jira",
            "query": f"Show me issues in {project}",
            "expect_data": True,
            "allow_no_data": True,
        })

    # ========== EDGE CASES ==========

    test_cases.extend([
        {
            "name": "Slack: Empty query handling",
            "datasource": "slack",
            "query": "   ",
            "expect_error": True,
        },
        {
            "name": "JIRA: Special characters in query",
            "datasource": "jira",
            "query": "Search for issues with 'quotes' and \"double quotes\"",
            "expect_data": True,
            "allow_no_data": True,
        },
        {
            "name": "Slack: Unicode name handling",
            "datasource": "slack",
            "query": "What is José working on?",
            "expect_data": True,
            "allow_no_data": True,
        },
    ])

    print(f"  Generated {len(test_cases)} test cases")

    # Phase 3: Execute Tests
    print("\n[PHASE 3] Executing Tests")
    print("-" * 40)

    for i, test_case in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] {test_case['datasource'].upper()}")
        result = await run_test(test_case)
        test_results["tests"].append(result)
        test_results["total_tests"] += 1

        if result["status"] == "PASSED":
            test_results["passed"] += 1
        elif result["status"] == "FAILED":
            test_results["failed"] += 1
        else:
            test_results["warnings"] += 1

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    test_results["end_time"] = datetime.now().isoformat()

    return test_results


def generate_report(results: dict) -> str:
    """Generate a comprehensive test report."""

    report = []
    report.append("=" * 70)
    report.append("COMPREHENSIVE TEST REPORT - ConnectorMCP")
    report.append("=" * 70)
    report.append("")
    report.append(f"Test Run: {results['start_time']} to {results['end_time']}")
    report.append("")

    # Summary
    report.append("## SUMMARY")
    report.append("-" * 40)
    total = results["total_tests"]
    passed = results["passed"]
    failed = results["failed"]
    warnings = results["warnings"]

    pass_rate = (passed / total * 100) if total > 0 else 0

    report.append(f"Total Tests:  {total}")
    report.append(f"Passed:       {passed} ({pass_rate:.1f}%)")
    report.append(f"Failed:       {failed}")
    report.append(f"Warnings:     {warnings}")
    report.append("")

    # Discovered Data
    report.append("## DISCOVERED DATA")
    report.append("-" * 40)

    if results["discovered_data"].get("slack_users"):
        report.append(f"Slack Users ({len(results['discovered_data']['slack_users'])}):")
        for user in results["discovered_data"]["slack_users"][:10]:
            report.append(f"  - {user}")

    if results["discovered_data"].get("jira_projects"):
        report.append(f"\nJIRA Projects ({len(results['discovered_data']['jira_projects'])}):")
        for project in results["discovered_data"]["jira_projects"]:
            report.append(f"  - {project}")

    if results["discovered_data"].get("jira_assignees"):
        report.append(f"\nJIRA Assignees ({len(results['discovered_data']['jira_assignees'])}):")
        for assignee in results["discovered_data"]["jira_assignees"][:10]:
            report.append(f"  - {assignee}")

    report.append("")

    # Failed Tests
    if failed > 0:
        report.append("## FAILED TESTS")
        report.append("-" * 40)
        for test in results["tests"]:
            if test["status"] == "FAILED":
                report.append(f"\n[FAILED] {test['test_name']}")
                report.append(f"  Query: {test['query']}")
                report.append(f"  Duration: {test['duration_ms']}ms")
                for issue in test["issues"]:
                    report.append(f"  Issue: {issue}")
                if test["response_preview"]:
                    report.append(f"  Response: {test['response_preview'][:200]}...")
        report.append("")

    # Warnings
    if warnings > 0:
        report.append("## WARNINGS")
        report.append("-" * 40)
        for test in results["tests"]:
            if test["status"] == "WARNING":
                report.append(f"\n[WARNING] {test['test_name']}")
                report.append(f"  Query: {test['query']}")
                for issue in test["issues"]:
                    report.append(f"  Issue: {issue}")
        report.append("")

    # All Test Details
    report.append("## ALL TEST RESULTS")
    report.append("-" * 40)

    # Group by datasource
    by_datasource = {}
    for test in results["tests"]:
        ds = test["datasource"]
        if ds not in by_datasource:
            by_datasource[ds] = []
        by_datasource[ds].append(test)

    for ds, tests in by_datasource.items():
        report.append(f"\n### {ds.upper()}")

        ds_passed = sum(1 for t in tests if t["status"] == "PASSED")
        ds_total = len(tests)
        report.append(f"Pass Rate: {ds_passed}/{ds_total} ({ds_passed/ds_total*100:.0f}%)")
        report.append("")

        for test in tests:
            status_icon = {"PASSED": "✓", "FAILED": "✗", "WARNING": "⚠"}.get(test["status"], "?")
            report.append(f"{status_icon} [{test['status']}] {test['test_name']} ({test['duration_ms']}ms)")
            if test["issues"]:
                for issue in test["issues"]:
                    report.append(f"    - {issue}")

    report.append("")
    report.append("=" * 70)
    report.append("END OF REPORT")
    report.append("=" * 70)

    return "\n".join(report)


async def main():
    """Main entry point."""
    print("Starting comprehensive test suite...")
    print("This will test various queries across all connectors.\n")

    results = await run_comprehensive_tests()

    # Generate and save report
    report = generate_report(results)

    report_path = "/Users/santoshnaranapatty/ConnectorMCP/backend/tests/test_report.txt"
    with open(report_path, "w") as f:
        f.write(report)

    print("\n" + report)
    print(f"\nReport saved to: {report_path}")

    # Also save JSON results
    json_path = "/Users/santoshnaranapatty/ConnectorMCP/backend/tests/test_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"JSON results saved to: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())

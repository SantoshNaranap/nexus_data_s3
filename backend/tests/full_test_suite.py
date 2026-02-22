#!/usr/bin/env python3
"""
Full Comprehensive Test Suite for ConnectorMCP
Discovers actual data and tests various scenarios.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any, List, Dict
import httpx

BASE_URL = "http://localhost:8000"

# Results
results = {
    "start_time": None,
    "end_time": None,
    "discovered": {},
    "tests": [],
    "summary": {"total": 0, "passed": 0, "failed": 0, "warnings": 0}
}


async def query(datasource: str, message: str, timeout: float = 120.0) -> dict:
    """Send query and get response."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/api/chat/message",
                json={"message": message, "datasource": datasource},
            )
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
            return resp.json()
        except Exception as e:
            return {"error": str(e)}


async def discover_slack_users() -> List[str]:
    """Get list of actual Slack users."""
    print("  Querying Slack users...")
    resp = await query("slack", "List all users in the workspace with their names")

    users = []
    content = resp.get("message", "")

    # Extract names from table format (| Name | ... |)
    for line in content.split("\n"):
        if "|" in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")]
            for p in parts:
                if p and len(p) > 2 and len(p) < 40:
                    # Skip headers and common words
                    if p.lower() not in ["name", "status", "email", "title", "role", "department", ""]:
                        # Likely a name
                        if " " in p or p[0].isupper():
                            users.append(p)

    # Dedupe and limit
    users = list(dict.fromkeys(users))[:15]
    return users


async def discover_jira_data() -> Dict:
    """Get JIRA projects and assignees."""
    print("  Querying JIRA projects...")
    data = {"projects": [], "assignees": []}

    # Get projects
    resp = await query("jira", "List all JIRA projects with their keys")
    content = resp.get("message", "")

    # Extract project keys (2-10 uppercase letters)
    keys = re.findall(r'\b([A-Z]{2,10})\b', content)
    # Filter likely project keys (exclude common words like AND, THE, etc)
    common = {"AND", "THE", "FOR", "ARE", "NOT", "BUT", "HAS", "WAS", "HIS", "HER", "ALL", "CAN", "HAD", "ONE", "TWO"}
    data["projects"] = [k for k in list(dict.fromkeys(keys)) if k not in common][:8]

    # Get assignees from open issues
    print("  Querying JIRA assignees...")
    resp = await query("jira", "Show me 20 open issues with their assignees")
    content = resp.get("message", "")

    # Extract names (First Last format)
    names = re.findall(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b', content)
    data["assignees"] = list(dict.fromkeys(names))[:10]

    return data


async def run_test(name: str, datasource: str, query_text: str, checks: dict = None) -> dict:
    """Run a single test and evaluate."""
    print(f"    Testing: {name}")

    start = time.time()
    resp = await query(datasource, query_text)
    duration = int((time.time() - start) * 1000)

    result = {
        "name": name,
        "datasource": datasource,
        "query": query_text,
        "duration_ms": duration,
        "status": "PASSED",
        "issues": [],
        "response_preview": "",
    }

    if "error" in resp:
        result["status"] = "FAILED"
        result["issues"].append(f"Error: {resp['error']}")
        return result

    content = resp.get("message", "")
    result["response_preview"] = content[:300] + "..." if len(content) > 300 else content

    checks = checks or {}

    # Check for no data
    no_data_phrases = ["no results", "no data", "couldn't find", "not found", "0 results", "no issues", "no messages", "no activity"]
    has_no_data = any(p in content.lower() for p in no_data_phrases)

    if checks.get("expect_data") and has_no_data:
        if not checks.get("allow_empty"):
            result["status"] = "WARNING"
            result["issues"].append("Expected data but got empty/no results")

    if checks.get("expect_error"):
        error_phrases = ["error", "not found", "invalid", "failed"]
        if not any(p in content.lower() for p in error_phrases):
            result["status"] = "WARNING"
            result["issues"].append("Expected error message but got normal response")

    if checks.get("must_contain"):
        for term in checks["must_contain"]:
            if term.lower() not in content.lower():
                result["status"] = "WARNING"
                result["issues"].append(f"Missing expected term: '{term}'")

    if checks.get("must_not_contain"):
        for term in checks["must_not_contain"]:
            if term.lower() in content.lower():
                result["status"] = "FAILED"
                result["issues"].append(f"Contains forbidden term: '{term}'")

    if checks.get("expect_sources"):
        if "sources" not in content.lower() and "source:" not in content.lower():
            result["issues"].append("Missing Sources section")

    # Print result
    icon = {"PASSED": "✓", "FAILED": "✗", "WARNING": "⚠"}.get(result["status"], "?")
    print(f"      {icon} {result['status']} ({duration}ms)")
    if result["issues"]:
        for issue in result["issues"][:2]:
            print(f"        - {issue}")

    return result


async def main():
    global results

    print("\n" + "=" * 70)
    print("COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    results["start_time"] = datetime.now().isoformat()

    # ===== DISCOVERY =====
    print("\n[PHASE 1] Discovery")
    print("-" * 40)

    slack_users = await discover_slack_users()
    results["discovered"]["slack_users"] = slack_users
    print(f"  Found {len(slack_users)} Slack users: {slack_users[:5]}...")

    jira = await discover_jira_data()
    results["discovered"]["jira_projects"] = jira["projects"]
    results["discovered"]["jira_assignees"] = jira["assignees"]
    print(f"  Found {len(jira['projects'])} JIRA projects: {jira['projects']}")
    print(f"  Found {len(jira['assignees'])} JIRA assignees: {jira['assignees'][:5]}...")

    # ===== TESTS =====
    print("\n[PHASE 2] Running Tests")
    print("-" * 40)

    tests = []

    # ----- SLACK PERSON TESTS -----
    print("\n  >> SLACK PERSON QUERIES")
    for user in slack_users[:5]:
        first_name = user.split()[0] if " " in user else user
        tests.append(await run_test(
            f"Slack: Activity for {first_name}",
            "slack",
            f"What is {first_name} working on?",
            {"expect_data": True, "allow_empty": True, "expect_sources": True}
        ))

    # Test DM history
    if slack_users:
        first = slack_users[0].split()[0]
        tests.append(await run_test(
            f"Slack: DM with {first}",
            "slack",
            f"What did {first} last say to me?",
            {"expect_data": True, "allow_empty": True}
        ))

    # Test non-existent person
    tests.append(await run_test(
        "Slack: Non-existent person",
        "slack",
        "What is Zyxwvutsrq Mcfakename working on?",
        {"expect_error": True, "must_contain": ["not found"]}
    ))

    # ----- SLACK CHANNEL TESTS -----
    print("\n  >> SLACK CHANNEL QUERIES")
    tests.append(await run_test(
        "Slack: List channels",
        "slack",
        "What channels are available?",
        {"expect_data": True}
    ))

    tests.append(await run_test(
        "Slack: Read general",
        "slack",
        "Show me recent messages in #general",
        {"expect_data": True, "allow_empty": True}
    ))

    tests.append(await run_test(
        "Slack: Search keyword",
        "slack",
        "Search for messages about deployment",
        {"expect_data": True, "allow_empty": True}
    ))

    # ----- JIRA PERSON TESTS -----
    print("\n  >> JIRA PERSON QUERIES")
    for assignee in jira["assignees"][:3]:
        first_name = assignee.split()[0]
        tests.append(await run_test(
            f"JIRA: Work for {first_name}",
            "jira",
            f"What is {first_name} working on?",
            {"expect_data": True, "allow_empty": True, "expect_sources": True}
        ))

    # Non-existent person
    tests.append(await run_test(
        "JIRA: Non-existent person",
        "jira",
        "What is Fakeperson Notreal working on?",
        {"expect_error": True, "must_contain": ["not found"]}
    ))

    # ----- JIRA PROJECT TESTS -----
    print("\n  >> JIRA PROJECT QUERIES")
    for project in jira["projects"][:2]:
        tests.append(await run_test(
            f"JIRA: Issues in {project}",
            "jira",
            f"Show me open issues in {project}",
            {"expect_data": True, "allow_empty": True, "expect_sources": True}
        ))

    # ----- JIRA ANALYTICAL TESTS -----
    print("\n  >> JIRA ANALYTICAL QUERIES")
    tests.append(await run_test(
        "JIRA: Behind schedule",
        "jira",
        "What projects are behind schedule?",
        {"expect_data": True, "allow_empty": True, "must_not_contain": ["here are all the projects", "list of projects"]}
    ))

    tests.append(await run_test(
        "JIRA: Overdue issues",
        "jira",
        "Show me overdue issues",
        {"expect_data": True, "allow_empty": True}
    ))

    tests.append(await run_test(
        "JIRA: Blocked issues",
        "jira",
        "What issues are blocked?",
        {"expect_data": True, "allow_empty": True}
    ))

    tests.append(await run_test(
        "JIRA: Bug count",
        "jira",
        "How many open bugs are there?",
        {"expect_data": True}
    ))

    tests.append(await run_test(
        "JIRA: In review",
        "jira",
        "What's stuck in code review?",
        {"expect_data": True, "allow_empty": True}
    ))

    # ----- EDGE CASES -----
    print("\n  >> EDGE CASES")
    tests.append(await run_test(
        "Empty query (should fail gracefully)",
        "slack",
        "   ",
        {"expect_error": True}
    ))

    tests.append(await run_test(
        "Unicode in name",
        "slack",
        "What is José doing?",
        {"expect_data": True, "allow_empty": True}
    ))

    tests.append(await run_test(
        "Special chars in query",
        "jira",
        "Search for issues with 'quotes' and \"double quotes\"",
        {"expect_data": True, "allow_empty": True}
    ))

    # Ambiguous name test
    tests.append(await run_test(
        "Slack: Ambiguous name (John)",
        "slack",
        "What is John working on?",
        {"expect_data": True, "allow_empty": True}
    ))

    # Store results
    results["tests"] = tests

    # ===== SUMMARY =====
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    passed = sum(1 for t in tests if t["status"] == "PASSED")
    failed = sum(1 for t in tests if t["status"] == "FAILED")
    warnings = sum(1 for t in tests if t["status"] == "WARNING")
    total = len(tests)

    results["summary"] = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "N/A"
    }

    print(f"\nTotal: {total} tests")
    print(f"  ✓ Passed:   {passed}")
    print(f"  ✗ Failed:   {failed}")
    print(f"  ⚠ Warnings: {warnings}")
    print(f"\nPass Rate: {results['summary']['pass_rate']}")

    # Show failures
    if failed > 0:
        print("\n--- FAILED TESTS ---")
        for t in tests:
            if t["status"] == "FAILED":
                print(f"\n✗ {t['name']}")
                print(f"  Query: {t['query']}")
                for issue in t["issues"]:
                    print(f"  Issue: {issue}")

    # Show warnings
    if warnings > 0:
        print("\n--- WARNINGS ---")
        for t in tests:
            if t["status"] == "WARNING":
                print(f"\n⚠ {t['name']}")
                print(f"  Query: {t['query']}")
                for issue in t["issues"]:
                    print(f"  Issue: {issue}")

    # Save report
    results["end_time"] = datetime.now().isoformat()

    report_path = "/Users/santoshnaranapatty/ConnectorMCP/backend/tests/full_test_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved to: {report_path}")

    # Generate markdown report
    md_report = generate_markdown_report(results)
    md_path = "/Users/santoshnaranapatty/ConnectorMCP/backend/tests/TEST_REPORT.md"
    with open(md_path, "w") as f:
        f.write(md_report)
    print(f"Markdown report saved to: {md_path}")

    return results


def generate_markdown_report(results: dict) -> str:
    """Generate a markdown report."""
    lines = [
        "# ConnectorMCP Test Report",
        "",
        f"**Generated:** {results['end_time']}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total Tests | {results['summary']['total']} |",
        f"| Passed | {results['summary']['passed']} |",
        f"| Failed | {results['summary']['failed']} |",
        f"| Warnings | {results['summary']['warnings']} |",
        f"| **Pass Rate** | **{results['summary']['pass_rate']}** |",
        "",
        "## Discovered Data",
        "",
        "### Slack Users",
        "",
    ]

    for user in results["discovered"].get("slack_users", []):
        lines.append(f"- {user}")

    lines.extend([
        "",
        "### JIRA Projects",
        "",
    ])
    for proj in results["discovered"].get("jira_projects", []):
        lines.append(f"- {proj}")

    lines.extend([
        "",
        "### JIRA Assignees",
        "",
    ])
    for assignee in results["discovered"].get("jira_assignees", []):
        lines.append(f"- {assignee}")

    # Failed tests
    failed = [t for t in results["tests"] if t["status"] == "FAILED"]
    if failed:
        lines.extend([
            "",
            "## Failed Tests",
            "",
        ])
        for t in failed:
            lines.append(f"### {t['name']}")
            lines.append(f"- **Query:** {t['query']}")
            lines.append(f"- **Duration:** {t['duration_ms']}ms")
            lines.append("- **Issues:**")
            for issue in t["issues"]:
                lines.append(f"  - {issue}")
            lines.append("")

    # Warnings
    warnings = [t for t in results["tests"] if t["status"] == "WARNING"]
    if warnings:
        lines.extend([
            "",
            "## Warnings",
            "",
        ])
        for t in warnings:
            lines.append(f"### {t['name']}")
            lines.append(f"- **Query:** {t['query']}")
            for issue in t["issues"]:
                lines.append(f"  - {issue}")
            lines.append("")

    # All tests table
    lines.extend([
        "",
        "## All Tests",
        "",
        "| Status | Test | Duration | Issues |",
        "|--------|------|----------|--------|",
    ])

    for t in results["tests"]:
        icon = {"PASSED": "✓", "FAILED": "✗", "WARNING": "⚠"}.get(t["status"], "?")
        issues = "; ".join(t["issues"][:2]) if t["issues"] else "-"
        lines.append(f"| {icon} {t['status']} | {t['name']} | {t['duration_ms']}ms | {issues} |")

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())

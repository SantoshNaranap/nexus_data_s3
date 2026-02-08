"""
E2E Tests for JIRA Connector

Tests conversational queries against JIRA with accuracy validation.
Tests across multiple projects to ensure generic functionality.
"""

import asyncio
import pytest
from datetime import datetime
from typing import List, Dict, Optional

from .test_framework import (
    TestRunner,
    TestSuiteResult,
    TestStatus,
    DirectAPIClient,
)


class JiraDirectAPI(DirectAPIClient):
    """Extended JIRA API client for validation."""

    async def get_project_issues(self, project_key: str, max_results: int = 20) -> List[Dict]:
        """Get issues for a specific project."""
        jql = f"project = {project_key} ORDER BY updated DESC"
        return await self.search_jira_issues(jql, max_results)

    async def get_project_issues_by_status(self, project_key: str, status: str) -> List[Dict]:
        """Get issues by status for a project."""
        jql = f'project = {project_key} AND status = "{status}"'
        return await self.search_jira_issues(jql)

    async def get_project_issues_in_sprint(self, project_key: str, sprint_name: str = None) -> List[Dict]:
        """Get issues in a sprint."""
        if sprint_name:
            jql = f'project = {project_key} AND sprint = "{sprint_name}"'
        else:
            jql = f'project = {project_key} AND sprint in openSprints()'
        return await self.search_jira_issues(jql)

    async def get_blocked_issues(self, project_key: str) -> List[Dict]:
        """Get blocked issues for a project."""
        jql = f'project = {project_key} AND (status = "Blocked" OR labels = "blocked" OR "flagged" = "Impediment")'
        return await self.search_jira_issues(jql)


class TestJiraConnector:
    """E2E tests for JIRA connector functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test runner for each test."""
        self.runner = TestRunner()
        self.direct_api = JiraDirectAPI()

    @pytest.mark.asyncio
    async def test_list_projects(self):
        """Test listing all JIRA projects."""
        suite = TestSuiteResult(suite_name="JIRA Project Listing", connector="jira")

        # Get actual projects from JIRA API
        actual_projects = await self.direct_api.get_jira_projects()
        project_names = [p.get("name") for p in actual_projects]
        project_keys = [p.get("key") for p in actual_projects]

        if not project_names:
            pytest.skip("No JIRA projects available or credentials not configured")

        # Test the chat query
        result = await self.runner.run_test_case(
            name="List all projects",
            query="What JIRA projects do I have?",
            datasource="jira",
            expected_contains=project_names[:3],  # Check for first 3 projects
            validation_data={"projects": project_names, "keys": project_keys},
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        assert result.status == TestStatus.PASSED, f"Failed: {result.error_message}"

    @pytest.mark.asyncio
    async def test_project_status_oralia(self):
        """Test getting status of Oralia V2 project."""
        suite = TestSuiteResult(suite_name="Oralia V2 Status", connector="jira")

        # Search for Oralia project
        projects = await self.direct_api.get_jira_projects()
        oralia_key = None
        for p in projects:
            if "oralia" in p.get("name", "").lower() or "oralia" in p.get("key", "").lower():
                oralia_key = p.get("key")
                break

        if not oralia_key:
            pytest.skip("Oralia project not found")

        # Get actual issue counts
        all_issues = await self.direct_api.get_project_issues(oralia_key)
        open_count = len([i for i in all_issues if i.get("fields", {}).get("status", {}).get("name") not in ["Done", "Closed"]])

        # Test the chat query
        result = await self.runner.run_test_case(
            name="Oralia V2 status",
            query="What's the status of Oralia V2 project?",
            datasource="jira",
            expected_contains=["oralia"],
            validation_data={"issue_count": len(all_issues), "open_count": open_count},
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_sprint_report(self):
        """Test getting sprint report for a project."""
        suite = TestSuiteResult(suite_name="Sprint Report", connector="jira")

        # Find a project with sprints
        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        # Try first few projects
        test_project = None
        for p in projects[:3]:
            issues = await self.direct_api.get_project_issues_in_sprint(p.get("key"))
            if issues:
                test_project = p
                break

        if not test_project:
            pytest.skip("No projects with active sprints found")

        project_name = test_project.get("name")

        result = await self.runner.run_test_case(
            name=f"Sprint report for {project_name}",
            query=f"Show me the sprint report for {project_name}",
            datasource="jira",
            expected_contains=[],
        )

        # Validate response mentions sprint-related content
        if result.response:
            sprint_indicators = ["sprint", "issue", "story", "task", "progress", "done", "todo"]
            found = sum(1 for ind in sprint_indicators if ind in result.response.lower())
            if found >= 2:
                result.status = TestStatus.PASSED
            else:
                result.status = TestStatus.FAILED
                result.error_message = "Response doesn't contain sprint information"

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_blocked_issues(self):
        """Test finding blocked issues in a project."""
        suite = TestSuiteResult(suite_name="Blocked Issues", connector="jira")

        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        # Test with first available project
        test_project = projects[0].get("name")

        result = await self.runner.run_test_case(
            name=f"Blocked issues in {test_project}",
            query=f"What issues are blocked in {test_project}?",
            datasource="jira",
            expected_contains=[],
        )

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)
        # Pass if no error
        assert result.status != TestStatus.ERROR, f"Error: {result.error_message}"

    @pytest.mark.asyncio
    async def test_deep_dive(self):
        """Test deep dive analysis of a project."""
        suite = TestSuiteResult(suite_name="Project Deep Dive", connector="jira")

        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        test_project = projects[0].get("name")

        result = await self.runner.run_test_case(
            name=f"Deep dive: {test_project}",
            query=f"Give me a deep dive analysis of the {test_project} project - status, blockers, upcoming work",
            datasource="jira",
            expected_contains=[],
        )

        # Validate comprehensive response
        if result.response and len(result.response) > 200:
            result.status = TestStatus.PASSED
        elif result.status != TestStatus.ERROR:
            result.status = TestStatus.FAILED
            result.error_message = "Response too brief for a deep dive"

        suite.results.append(result)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_conversation_context_project(self):
        """Test context is maintained when discussing a project."""
        suite = TestSuiteResult(suite_name="Project Context", connector="jira")

        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        test_project = projects[0].get("name")

        # Multi-turn conversation about a project
        results = await self.runner.run_conversation_test(
            name="Project context",
            queries=[
                (f"Tell me about the {test_project} project", []),
                ("What issues are in progress there?", []),  # Should maintain project context
                ("Who is working on the most issues?", []),  # Should still be same project
                ("Show me blocked items", []),  # Context maintained
            ],
            datasource="jira",
        )

        suite.results.extend(results)
        suite.end_time = datetime.now()

        self.runner.print_results(suite)


class TestJiraMultiProject:
    """Tests across multiple projects to ensure generic functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()
        self.direct_api = JiraDirectAPI()

    @pytest.mark.asyncio
    async def test_all_projects_same_questions(self):
        """Test the same set of questions across all available projects."""
        suite = TestSuiteResult(suite_name="Multi-Project Tests", connector="jira")

        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        # Standard questions to ask about each project
        questions = [
            ("What's the status of {project}?", "status"),
            ("Show me open issues in {project}", "open issues"),
            ("What's blocked in {project}?", "blocked"),
            ("Show the sprint for {project}", "sprint"),
        ]

        # Test top 3 projects
        for project in projects[:3]:
            project_name = project.get("name")
            project_key = project.get("key")

            print(f"\nTesting project: {project_name} ({project_key})")

            for question_template, desc in questions[:2]:  # Test first 2 questions per project
                question = question_template.format(project=project_name)

                result = await self.runner.run_test_case(
                    name=f"{project_name}: {desc}",
                    query=question,
                    datasource="jira",
                    expected_contains=[],
                )

                suite.results.append(result)

                # Reset session between projects
                self.runner.chat_client.reset_session()

        suite.end_time = datetime.now()
        self.runner.print_results(suite)

    @pytest.mark.asyncio
    async def test_sensihire_project(self):
        """Test specifically with SensiHire project if it exists."""
        suite = TestSuiteResult(suite_name="SensiHire Tests", connector="jira")

        projects = await self.direct_api.get_jira_projects()

        # Find sensihire project
        sensihire = None
        for p in projects:
            name = p.get("name", "").lower()
            key = p.get("key", "").lower()
            if "sensihire" in name or "sensihire" in key:
                sensihire = p
                break

        if not sensihire:
            pytest.skip("SensiHire project not found")

        project_name = sensihire.get("name")

        # Run same tests as Oralia
        result = await self.runner.run_test_case(
            name="SensiHire status",
            query=f"What's the status of {project_name}?",
            datasource="jira",
            expected_contains=[],
        )
        suite.results.append(result)

        result = await self.runner.run_test_case(
            name="SensiHire sprint",
            query=f"Show me the current sprint for {project_name}",
            datasource="jira",
            expected_contains=[],
        )
        suite.results.append(result)

        result = await self.runner.run_test_case(
            name="SensiHire deep dive",
            query=f"Give me a deep dive on {project_name}",
            datasource="jira",
            expected_contains=[],
        )
        suite.results.append(result)

        suite.end_time = datetime.now()
        self.runner.print_results(suite)


class TestJiraAccuracy:
    """Accuracy-focused tests comparing chat responses with direct API calls."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = TestRunner()
        self.direct_api = JiraDirectAPI()

    @pytest.mark.asyncio
    async def test_issue_count_accuracy(self):
        """Verify the chat accurately reports issue counts."""
        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        project = projects[0]
        project_name = project.get("name")
        project_key = project.get("key")

        # Get actual count
        actual_issues = await self.direct_api.get_project_issues(project_key, 100)
        actual_count = len(actual_issues)

        # Ask chat for count
        result = await self.runner.run_test_case(
            name="Issue count accuracy",
            query=f"How many issues are in {project_name}?",
            datasource="jira",
            expected_contains=[],
        )

        # Check if the number mentioned is close to actual
        import re
        numbers = re.findall(r'\b(\d+)\b', result.response)
        if numbers:
            # Find the most likely count number (not dates, etc.)
            for num in numbers:
                reported_count = int(num)
                if 1 < reported_count < 10000:  # Reasonable issue count range
                    variance = abs(reported_count - actual_count) / max(actual_count, 1)
                    if variance <= 0.2:  # 20% tolerance
                        result.status = TestStatus.PASSED
                        result.accuracy_score = 100 - (variance * 100)
                        break
            else:
                result.status = TestStatus.FAILED
                result.error_message = f"No close count match found. Actual: {actual_count}"
        else:
            result.status = TestStatus.FAILED
            result.error_message = "No numbers found in response"

        self.runner.print_results(
            TestSuiteResult(
                suite_name="Issue Count Accuracy",
                connector="jira",
                results=[result],
                end_time=datetime.now(),
            )
        )

    @pytest.mark.asyncio
    async def test_no_hallucinated_issues(self):
        """Verify chat doesn't invent issue keys."""
        projects = await self.direct_api.get_jira_projects()
        if not projects:
            pytest.skip("No JIRA projects available")

        project = projects[0]
        project_name = project.get("name")
        project_key = project.get("key")

        # Get actual issue keys
        actual_issues = await self.direct_api.get_project_issues(project_key, 50)
        valid_keys = [i.get("key") for i in actual_issues]

        # Ask for issues
        result = await self.runner.run_test_case(
            name="No hallucinated issues",
            query=f"List the issues in {project_name}",
            datasource="jira",
            expected_contains=[],
        )

        # Extract issue keys from response
        import re
        # JIRA key pattern: PROJECT-123
        found_keys = re.findall(rf'{project_key}-\d+', result.response)

        if found_keys:
            # Check if found keys are valid
            invalid_keys = [k for k in found_keys if k not in valid_keys]
            if invalid_keys:
                result.status = TestStatus.FAILED
                result.error_message = f"Possible hallucinated issues: {invalid_keys[:5]}"
            else:
                result.status = TestStatus.PASSED
                result.actual_matches = found_keys[:5]
        else:
            # No specific keys mentioned - could be a summary
            if len(result.response) > 50:
                result.status = TestStatus.PASSED  # Response exists but no keys

        self.runner.print_results(
            TestSuiteResult(
                suite_name="Hallucination Check",
                connector="jira",
                results=[result],
                end_time=datetime.now(),
            )
        )


# Standalone runner for quick testing
async def run_all_jira_tests():
    """Run all JIRA tests and save results."""
    runner = TestRunner()
    direct_api = JiraDirectAPI()

    print("\n" + "=" * 80)
    print("JIRA CONNECTOR E2E TESTS")
    print("=" * 80)

    suite = TestSuiteResult(suite_name="Complete JIRA Test Suite", connector="jira")

    # Get projects for testing
    projects = await direct_api.get_jira_projects()
    if not projects:
        print("ERROR: No JIRA projects available. Check credentials.")
        return None

    print(f"Found {len(projects)} projects: {[p.get('name') for p in projects[:5]]}")

    # Test 1: List projects
    print("\n[1/8] Testing project listing...")
    project_names = [p.get("name") for p in projects[:5]]
    result = await runner.run_test_case(
        name="List projects",
        query="What JIRA projects do I have?",
        datasource="jira",
        expected_contains=project_names[:3],
    )
    suite.results.append(result)

    # Test 2: Oralia V2 status
    print("\n[2/8] Testing Oralia V2 status...")
    result = await runner.run_test_case(
        name="Oralia V2 status",
        query="What's the status of Oralia V2?",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 3: Sprint report
    print("\n[3/8] Testing sprint report...")
    result = await runner.run_test_case(
        name="Sprint report",
        query="Show me the sprint report for Oralia V2",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 4: Deep dive
    print("\n[4/8] Testing deep dive...")
    result = await runner.run_test_case(
        name="Deep dive",
        query="Give me a deep dive on the Oralia V2 project",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 5: Blocked issues
    print("\n[5/8] Testing blocked issues...")
    result = await runner.run_test_case(
        name="Blocked issues",
        query="What issues are blocked in Oralia V2?",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 6: SensiHire (if exists)
    print("\n[6/8] Testing SensiHire project...")
    result = await runner.run_test_case(
        name="SensiHire status",
        query="What's the status of SensiHire?",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 7: Multi-project comparison
    print("\n[7/8] Testing multi-project query...")
    runner.chat_client.reset_session()
    result = await runner.run_test_case(
        name="Compare projects",
        query="Compare the status of Oralia V2 and SensiHire projects",
        datasource="jira",
        expected_contains=[],
    )
    suite.results.append(result)

    # Test 8: Conversation context
    print("\n[8/8] Testing conversation context...")
    runner.chat_client.reset_session()
    results = await runner.run_conversation_test(
        name="Conversation",
        queries=[
            ("Tell me about Oralia V2", []),
            ("What issues are in progress?", []),
            ("Who is assigned the most?", []),
        ],
        datasource="jira",
    )
    suite.results.extend(results)

    suite.end_time = datetime.now()
    runner.print_results(suite)

    # Save results
    runner.results.append(suite)
    runner.save_results("test_results_jira.json")

    return suite


if __name__ == "__main__":
    asyncio.run(run_all_jira_tests())

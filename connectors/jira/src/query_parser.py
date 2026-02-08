"""Natural language query parser for JIRA."""

import re
import logging
from typing import Dict, List, Optional, Any
from difflib import get_close_matches

logger = logging.getLogger("jira-query-parser")


class JiraQueryParser:
    """Parse natural language queries into JQL."""

    def __init__(self, jira_client):
        self.jira_client = jira_client
        self._projects_cache = None
        self._assignees_cache = None

    def _get_projects(self) -> List[Dict[str, str]]:
        """Get all projects with caching."""
        if self._projects_cache is None:
            projects = self.jira_client.projects()
            self._projects_cache = [
                {"key": p.key, "name": p.name.lower()} for p in projects
            ]
        return self._projects_cache

    def _get_assignees(self, project_key: Optional[str] = None) -> List[str]:
        """Get all assignees with caching."""
        if self._assignees_cache is None:
            # Get all issues with assignees
            jql = "assignee is not EMPTY"
            if project_key:
                jql += f" AND project = {project_key}"

            issues = self.jira_client.search_issues(jql, maxResults=1000, fields="assignee")

            # Extract unique assignee names
            assignees = set()
            for issue in issues:
                if hasattr(issue.fields, "assignee") and issue.fields.assignee:
                    assignees.add(issue.fields.assignee.displayName)

            self._assignees_cache = list(assignees)

        return self._assignees_cache

    def _match_project(self, query: str) -> Optional[str]:
        """Match project name in query to project key."""
        projects = self._get_projects()
        query_lower = query.lower()

        # Normalize query: replace hyphens with spaces for matching
        query_normalized = query_lower.replace("-", " ").replace("_", " ")

        # DEBUG: Log all available projects
        logger.info(f"[MATCH_PROJECT] Query: '{query_lower}'")
        logger.info(f"[MATCH_PROJECT] Query normalized: '{query_normalized}'")
        logger.info(f"[MATCH_PROJECT] Available projects: {[(p['key'], p['name']) for p in projects]}")

        # PRIORITY 0: Look for explicit "what's in X" or "show X" patterns at the END of query
        # This handles cases like "oralia: nice, now show me sensi hire" - we want sensi hire
        explicit_patterns = [
            r"(?:show|what'?s?\s+(?:in|there\s+in)|tell\s+me\s+about|let'?s?\s+see)\s+([a-z0-9][\w\s-]+?)(?:\s+(?:project|though|please|now))?$",
            r"(?:in|about|for)\s+([a-z0-9][\w\s-]+?)(?:\s+(?:project|though|please))?$",
        ]
        for pattern in explicit_patterns:
            match = re.search(pattern, query_lower)
            if match:
                target_name = match.group(1).strip()
                target_normalized = target_name.replace("-", " ").replace("_", " ")
                logger.info(f"[MATCH_PROJECT] Explicit pattern found target: '{target_name}' (normalized: '{target_normalized}')")

                # Try to match this specific target
                for project in projects:
                    name_lower = project["name"].lower()
                    name_normalized = name_lower.replace("-", " ").replace("_", " ")
                    if name_normalized == target_normalized or name_lower == target_name:
                        logger.info(f"[MATCH_PROJECT] EXPLICIT match: '{project['key']}' from pattern")
                        return project["key"]
                    # Also check if target is a substring
                    if target_normalized in name_normalized or name_normalized in target_normalized:
                        logger.info(f"[MATCH_PROJECT] EXPLICIT substring match: '{project['key']}'")
                        return project["key"]

        # PRIORITY 1: Exact name match with normalization (handles "sensi hire" vs "sensi-hire")
        # Prefer matches that appear LATER in the query (what user is asking about NOW)
        name_matches = []
        for project in projects:
            name_lower = project["name"].lower()
            name_normalized = name_lower.replace("-", " ").replace("_", " ")

            # Check both original and normalized versions
            for name_to_check in [name_lower, name_normalized]:
                for query_to_check in [query_lower, query_normalized]:
                    if name_to_check in query_to_check:
                        # Find position in query (later = more relevant)
                        pos = query_to_check.rfind(name_to_check)
                        name_matches.append((pos, len(name_to_check), project["key"], project["name"]))
                        break  # Don't double-count same project

        if name_matches:
            # Sort by position (highest = latest mention), then by length descending
            name_matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
            best_match = name_matches[0]
            logger.info(f"[MATCH_PROJECT] PRIORITY 1 match: name '{best_match[3]}' at pos {best_match[0]} (of {len(name_matches)} candidates)")
            return best_match[2]

        # PRIORITY 1: Exact key match - prefer LONGER matches to avoid "ORAI" matching over "ORALIA"
        # Sort candidates by key length (descending) so longer keys match first
        key_matches = []
        for project in projects:
            key_lower = project["key"].lower()
            if key_lower in query_lower:
                key_matches.append((len(key_lower), project["key"]))

        if key_matches:
            # Sort by length descending, return longest match
            key_matches.sort(reverse=True)
            best_match = key_matches[0][1]
            logger.info(f"[MATCH_PROJECT] PRIORITY 1 match: key '{best_match}' (longest of {len(key_matches)} candidates)")
            return best_match

        # PRIORITY 2: Partial name match (for cases where name isn't an exact substring)
        for project in projects:
            # Check if any significant word from project name appears in query
            name_words = project["name"].lower().replace("-", " ").replace("_", " ").split()
            for word in name_words:
                if len(word) >= 4 and word in query_lower:  # Only match words 4+ chars
                    logger.info(f"[MATCH_PROJECT] PRIORITY 2 match: word '{word}' from '{project['name']}' found in query")
                    return project["key"]

        # PRIORITY 3: Match project names that include version numbers or suffixes
        # Check for versioned project names like "project-v2", "project_v2", "project 2"
        version_pattern = r"([\w]+)[-_\s]?v?(\d+)"
        query_version_match = re.search(version_pattern, query_lower)
        if query_version_match:
            base_name = query_version_match.group(1)
            version = query_version_match.group(2)
            logger.info(f"[MATCH_PROJECT] PRIORITY 3: extracted base='{base_name}', version='{version}' from query")
            for project in projects:
                # Check if project name contains base + version
                project_version_match = re.search(version_pattern, project["name"])
                if project_version_match:
                    proj_base = project_version_match.group(1)
                    proj_version = project_version_match.group(2)
                    logger.info(f"[MATCH_PROJECT] PRIORITY 3: project '{project['name']}' has base='{proj_base}', version='{proj_version}'")
                    if base_name == proj_base and version == proj_version:
                        logger.info(f"[MATCH_PROJECT] PRIORITY 3 match!")
                        return project["key"]

        # PRIORITY 4: Normalized match (stripping version - but only if no version-specific match)
        query_normalized = re.sub(r"[-_\s]+v?\d*$", "", query_lower)  # Only strip suffix, not middle parts
        logger.info(f"[MATCH_PROJECT] PRIORITY 4: query_normalized='{query_normalized}'")
        for project in projects:
            project_name_normalized = re.sub(r"[-_\s]+v?\d*$", "", project["name"])
            if project_name_normalized and project_name_normalized in query_normalized:
                logger.info(f"[MATCH_PROJECT] PRIORITY 4 match: '{project_name_normalized}' in '{query_normalized}'")
                return project["key"]

        # PRIORITY 5: Fuzzy match on project names (last resort)
        project_names = [p["name"] for p in projects]
        matches = get_close_matches(query_lower, project_names, n=1, cutoff=0.6)
        logger.info(f"[MATCH_PROJECT] PRIORITY 5: fuzzy matches={matches}")
        if matches:
            for project in projects:
                if project["name"] == matches[0]:
                    logger.info(f"[MATCH_PROJECT] PRIORITY 5 match: '{project['key']}'")
                    return project["key"]

        logger.warning(f"[MATCH_PROJECT] NO MATCH FOUND for query: '{query_lower}'")
        return None

    def _match_assignee(self, query: str, project_key: Optional[str] = None) -> Optional[str]:
        """Match person name in query to assignee."""
        assignees = self._get_assignees(project_key)
        query_lower = query.lower()

        # Enhanced name patterns to handle natural language variations
        # Matches: "what is austin working on", "what austin is working on", "show me austin's work", etc.
        name_patterns = [
            r"what\s+(?:is\s+)?(\w+)\s+(?:is\s+)?(?:work|doing|assigned)",  # "what is austin working" or "what austin is working"
            r"show\s+(?:me\s+)?(\w+)'?s?\s+(?:work|issues|tasks)",  # "show me austin's work"
            r"(\w+)\s+(?:is|has|does)\s+(?:work|task|issue|assigned)",  # "austin is working" or "austin has tasks"
            r"(\w+)'?s?\s+(?:work|issues|tasks|assignments)",  # "austin's work"
            r"assigned\s+to\s+(\w+)",  # "assigned to austin"
            r"(\w+)'?s?\s+(?:current|active|open)\s+(?:work|issues|tasks)",  # "austin's current work"
        ]

        extracted_name = None
        for pattern in name_patterns:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                extracted_name = match.group(1)
                # Skip common words that aren't names
                if extracted_name not in ["you", "me", "i", "we", "they", "tell", "can"]:
                    break
                extracted_name = None  # Reset if it was a common word

        if not extracted_name:
            return None

        # Try exact match (case-insensitive)
        for assignee in assignees:
            if extracted_name.lower() in assignee.lower():
                return assignee

        # Try fuzzy match on first names
        assignee_first_names = [a.split()[0].lower() for a in assignees]
        matches = get_close_matches(extracted_name.lower(), assignee_first_names, n=1, cutoff=0.7)
        if matches:
            for i, first_name in enumerate(assignee_first_names):
                if first_name == matches[0]:
                    return assignees[i]

        return None

    def _detect_status_filter(self, query: str) -> Optional[str]:
        """Detect status filters in query."""
        query_lower = query.lower()

        status_keywords = {
            "open": "status != Closed",
            "closed": "status = Closed",
            "in progress": 'status = "In Progress"',
            "backlog": "status = Backlog",
            "done": "status = Done",
            "todo": "status = To Do",
        }

        for keyword, jql in status_keywords.items():
            if keyword in query_lower:
                return jql

        # Default: exclude closed issues
        if "closed" not in query_lower:
            return "status != Closed"

        return None

    def _detect_issue_type(self, query: str) -> Optional[str]:
        """Detect issue type filters in query."""
        query_lower = query.lower()

        type_keywords = {
            "bug": 'type = Bug',
            "bugs": 'type = Bug',
            "task": 'type = Task',
            "tasks": 'type = Task',
            "story": 'type = Story',
            "stories": 'type = Story',
        }

        for keyword, jql in type_keywords.items():
            if keyword in query_lower:
                return jql

        return None

    def _detect_count_query(self, query: str) -> bool:
        """Detect if query is asking for a count."""
        query_lower = query.lower()
        count_keywords = ["how many", "count", "number of"]
        return any(keyword in query_lower for keyword in count_keywords)

    def parse(self, query: str) -> Dict[str, Any]:
        """
        Parse natural language query into structured data.

        Returns:
            {
                "jql": "generated JQL query",
                "is_count": bool,
                "matched_entities": {
                    "project": str or None,
                    "assignee": str or None,
                    "status": str or None,
                    "type": str or None,
                }
            }
        """
        # Extract entities
        project_key = self._match_project(query)
        assignee = self._match_assignee(query, project_key)
        status_filter = self._detect_status_filter(query)
        type_filter = self._detect_issue_type(query)
        is_count = self._detect_count_query(query)

        # Build JQL
        jql_parts = []

        if project_key:
            jql_parts.append(f"project = {project_key}")

        if assignee:
            jql_parts.append(f'assignee = "{assignee}"')

        if status_filter:
            jql_parts.append(status_filter)

        if type_filter:
            jql_parts.append(type_filter)

        # Default: get all non-closed issues if no specific filters
        if not jql_parts:
            jql_parts.append("status != Closed")

        jql = " AND ".join(jql_parts)

        return {
            "jql": jql,
            "is_count": is_count,
            "matched_entities": {
                "project": project_key,
                "assignee": assignee,
                "status": status_filter,
                "type": type_filter,
            },
        }

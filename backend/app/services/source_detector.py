"""
Source Detector Service for Multi-Source Agent Orchestration.

This module analyzes natural language queries to determine which data sources
are relevant and should be queried. It uses a combination of:
1. Rule-based keyword matching (fast, for common patterns)
2. LLM-based analysis (for complex or ambiguous queries)

The detector returns ranked sources with confidence scores to help the
agent orchestrator decide which sources to query.
"""

import logging
import re
import json
from typing import List, Dict, Any, Optional

from anthropic import APIError, APIConnectionError, RateLimitError

from app.services.claude_client import claude_client
from app.models.agent import DataSourceRelevance

# Configure logging for the source detector
logger = logging.getLogger(__name__)


class SourceDetector:
    """
    Detects which data sources are relevant for a given query.
    
    Uses a two-tier approach:
    1. Fast rule-based matching for clear patterns
    2. LLM-based analysis for complex queries
    
    This allows for sub-second detection in common cases while still
    handling edge cases intelligently.
    """

    def __init__(self):
        """Initialize the source detector with LLM client and keyword patterns."""
        # Use centralized Claude client
        self.client = claude_client.client

        # Define keyword patterns for each data source
        # These enable fast rule-based matching without LLM calls
        self._keyword_patterns = self._build_keyword_patterns()

        # Define source metadata for context
        self._source_metadata = self._build_source_metadata()

    def _build_keyword_patterns(self) -> Dict[str, Dict[str, Any]]:
        """
        Build keyword patterns for rule-based source detection.
        
        Returns a dictionary mapping datasource IDs to their detection patterns.
        Each pattern includes:
        - keywords: words that strongly indicate this source
        - negative_keywords: words that indicate NOT this source
        - weight: base confidence weight for keyword matches
        """
        return {
            "s3": {
                # Keywords that indicate S3/storage queries
                "keywords": [
                    "s3", "bucket", "buckets", "object", "objects", "file", "files",
                    "document", "documents", "storage", "aws", "upload", "download",
                    "blob", "archive", "pdf", "csv", "json file", "xml file",
                    "stored", "cloud storage", "read file", "file content"
                ],
                # Keywords that suggest NOT S3
                "negative_keywords": ["email", "calendar", "issue", "ticket", "order", "product"],
                # Base confidence weight for keyword matches
                "weight": 0.8,
            },
            "mysql": {
                # Keywords that indicate database queries
                "keywords": [
                    "mysql", "database", "db", "table", "tables", "sql", "query",
                    "record", "records", "row", "rows", "column", "columns",
                    "schema", "select", "insert", "update", "delete", "data warehouse",
                    "relational", "join", "aggregate", "count", "sum", "average"
                ],
                # Keywords that suggest NOT MySQL
                "negative_keywords": ["s3", "bucket", "jira", "issue", "email"],
                "weight": 0.8,
            },
            "jira": {
                # Keywords that indicate JIRA/project management queries
                "keywords": [
                    "jira", "issue", "issues", "ticket", "tickets", "bug", "bugs",
                    "task", "tasks", "story", "stories", "epic", "epics", "sprint",
                    "backlog", "project", "assignee", "assigned", "working on",
                    "status", "priority", "roadmap", "kanban", "scrum", "agile",
                    "developer", "qa", "testing", "release", "version"
                ],
                "negative_keywords": ["s3", "bucket", "order", "product", "email"],
                "weight": 0.85,
            },
            "shopify": {
                # Keywords that indicate e-commerce/Shopify queries
                "keywords": [
                    "shopify", "order", "orders", "product", "products", "customer",
                    "customers", "inventory", "stock", "sale", "sales", "revenue",
                    "store", "shop", "cart", "checkout", "shipping", "fulfillment",
                    "sku", "variant", "collection", "discount", "coupon", "refund"
                ],
                "negative_keywords": ["jira", "issue", "bug", "s3", "email"],
                "weight": 0.85,
            },
            "google_workspace": {
                # Keywords that indicate Google Workspace queries
                "keywords": [
                    "google", "gmail", "email", "emails", "inbox", "calendar",
                    "meeting", "meetings", "event", "events", "schedule", "drive",
                    "docs", "sheets", "slides", "spreadsheet", "presentation",
                    "document", "folder", "share", "collaborate", "workspace"
                ],
                "negative_keywords": ["s3", "bucket", "jira", "shopify", "order"],
                "weight": 0.8,
            },
        }

    def _build_source_metadata(self) -> Dict[str, Dict[str, str]]:
        """
        Build metadata about each data source for LLM context.
        
        This helps the LLM make better decisions about source relevance.
        """
        return {
            "s3": {
                "name": "Amazon S3",
                "description": "Cloud object storage for files, documents, and data",
                "best_for": "File storage, document retrieval, data lakes",
                "data_types": "Files, documents, PDFs, CSVs, JSON, images",
            },
            "mysql": {
                "name": "MySQL Database",
                "description": "Relational database for structured data",
                "best_for": "Structured queries, aggregations, reports",
                "data_types": "Structured records, tables, transactions",
            },
            "jira": {
                "name": "JIRA",
                "description": "Project management and issue tracking",
                "best_for": "Tasks, bugs, sprints, project status",
                "data_types": "Issues, projects, sprints, team workload",
            },
            "shopify": {
                "name": "Shopify",
                "description": "E-commerce platform for online stores",
                "best_for": "Orders, products, inventory, sales",
                "data_types": "Orders, products, customers, inventory",
            },
            "google_workspace": {
                "name": "Google Workspace",
                "description": "Productivity suite including Gmail, Drive, Calendar",
                "best_for": "Emails, documents, calendar events, collaboration",
                "data_types": "Emails, documents, spreadsheets, calendar events",
            },
        }

    def _rule_based_detection(self, query: str) -> List[DataSourceRelevance]:
        """
        Perform fast rule-based source detection using keyword matching.
        
        This is the first tier of detection - fast but less nuanced.
        Returns sources with confidence > 0.3 based on keyword matches.
        
        Args:
            query: The natural language query to analyze
            
        Returns:
            List of DataSourceRelevance objects sorted by confidence
        """
        results = []
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        
        for datasource, patterns in self._keyword_patterns.items():
            # Count keyword matches
            keyword_matches = sum(
                1 for kw in patterns["keywords"] 
                if kw.lower() in query_lower
            )
            
            # Count negative keyword matches (reduce confidence)
            negative_matches = sum(
                1 for kw in patterns["negative_keywords"]
                if kw.lower() in query_lower
            )
            
            # Calculate confidence score
            if keyword_matches > 0:
                # Base confidence from keyword matches
                base_confidence = min(keyword_matches * 0.2, 0.6)
                
                # Apply source weight
                confidence = base_confidence * patterns["weight"]
                
                # Reduce confidence for negative matches
                confidence -= negative_matches * 0.15
                
                # Ensure confidence is in valid range
                confidence = max(0.0, min(1.0, confidence))
                
                if confidence > 0.3:
                    # Generate reasoning based on matches
                    matched_keywords = [
                        kw for kw in patterns["keywords"]
                        if kw.lower() in query_lower
                    ]
                    
                    results.append(DataSourceRelevance(
                        datasource=datasource,
                        confidence=round(confidence, 2),
                        reasoning=f"Keywords matched: {', '.join(matched_keywords[:3])}",
                        suggested_approach=self._get_suggested_approach(datasource, query)
                    ))
        
        # Sort by confidence descending
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    def _get_suggested_approach(self, datasource: str, query: str) -> str:
        """
        Generate a suggested approach for querying a data source.
        
        Provides guidance to the agent on how to query this source.
        """
        query_lower = query.lower()
        
        if datasource == "s3":
            if "content" in query_lower or "read" in query_lower:
                return "List buckets, then objects, then read specific files"
            return "Use list_buckets to see available storage"
            
        elif datasource == "mysql":
            if "table" in query_lower:
                return "Use list_tables to see database schema"
            return "Use execute_query with appropriate SELECT statement"
            
        elif datasource == "jira":
            if any(name in query_lower for name in ["working on", "assigned", "who"]):
                return "Use query_jira with natural language to find assignee info"
            return "Use query_jira tool with the natural language query"
            
        elif datasource == "shopify":
            if "order" in query_lower:
                return "Use list_orders with appropriate filters"
            return "Use list_products or search_products"
            
        elif datasource == "google_workspace":
            if "email" in query_lower or "gmail" in query_lower:
                return "Use list_messages to retrieve emails"
            elif "calendar" in query_lower or "meeting" in query_lower:
                return "Use get_events to check calendar"
            return "Use search_drive_files to find documents"
            
        return "Query this source for relevant information"

    async def detect_sources_llm(
        self, 
        query: str,
        available_sources: List[str]
    ) -> List[DataSourceRelevance]:
        """
        Use LLM to analyze query and detect relevant sources.
        
        This is the second tier of detection - slower but more accurate.
        Used for complex or ambiguous queries where rule-based fails.
        
        Args:
            query: The natural language query to analyze
            available_sources: List of available datasource IDs
            
        Returns:
            List of DataSourceRelevance objects from LLM analysis
        """
        # Build context about available sources
        sources_context = "\n".join([
            f"- {src}: {self._source_metadata.get(src, {}).get('description', 'Unknown source')}"
            f" (best for: {self._source_metadata.get(src, {}).get('best_for', 'general queries')})"
            for src in available_sources
        ])
        
        # Create prompt for source detection
        prompt = f"""Analyze this user query and determine which data sources are relevant.

USER QUERY: "{query}"

AVAILABLE DATA SOURCES:
{sources_context}

For each relevant source, provide:
1. datasource: The source ID
2. confidence: A score from 0.0 to 1.0 (higher = more relevant)
3. reasoning: Why this source is relevant
4. suggested_approach: How to query this source

Respond with a JSON array of relevant sources. Only include sources with confidence >= 0.4.
If no sources are clearly relevant, return an empty array.

Example response:
[
  {{"datasource": "jira", "confidence": 0.9, "reasoning": "Query asks about tasks and assignments", "suggested_approach": "Use query_jira with natural language"}},
  {{"datasource": "mysql", "confidence": 0.5, "reasoning": "May need historical data from database", "suggested_approach": "Query project_metrics table"}}
]

JSON Response:"""

        try:
            # Use Haiku for fast, cost-effective source detection
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            
            # Extract JSON from response
            response_text = response.content[0].text.strip()
            
            # Find JSON array in response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                sources_data = json.loads(json_match.group())
                
                results = []
                for src in sources_data:
                    if src.get("datasource") in available_sources:
                        results.append(DataSourceRelevance(
                            datasource=src["datasource"],
                            confidence=min(1.0, max(0.0, src.get("confidence", 0.5))),
                            reasoning=src.get("reasoning", "LLM determined relevance"),
                            suggested_approach=src.get("suggested_approach", None)
                        ))
                
                return results

        except (APIError, APIConnectionError, RateLimitError) as e:
            logger.error(f"LLM API error during source detection: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error during source detection: {e}")

        return []

    async def detect_sources(
        self,
        query: str,
        available_sources: Optional[List[str]] = None,
        use_llm_fallback: bool = True
    ) -> List[DataSourceRelevance]:
        """
        Main method to detect relevant sources for a query.
        
        Uses a two-tier approach:
        1. Fast rule-based detection first
        2. LLM-based detection if rule-based is inconclusive
        
        Args:
            query: The natural language query
            available_sources: List of available datasources (None = all)
            use_llm_fallback: Whether to use LLM for complex queries
            
        Returns:
            List of DataSourceRelevance sorted by confidence
        """
        # Default to all sources if not specified
        if available_sources is None:
            available_sources = list(self._keyword_patterns.keys())
        
        # Filter patterns to only available sources
        logger.info(f"Detecting sources for query: {query[:100]}...")
        
        # Tier 1: Fast rule-based detection
        rule_results = self._rule_based_detection(query)
        
        # Filter to only available sources
        rule_results = [r for r in rule_results if r.datasource in available_sources]
        
        logger.info(f"Rule-based detection found {len(rule_results)} sources: "
                   f"{[r.datasource for r in rule_results]}")
        
        # If rule-based found high-confidence results, use them
        if rule_results and rule_results[0].confidence >= 0.6:
            logger.info("Using rule-based results (high confidence)")
            return rule_results
        
        # Tier 2: LLM-based detection for complex/ambiguous queries
        if use_llm_fallback:
            logger.info("Using LLM fallback for source detection")
            llm_results = await self.detect_sources_llm(query, available_sources)
            
            if llm_results:
                # Merge with rule-based results, preferring higher confidence
                merged = self._merge_results(rule_results, llm_results)
                logger.info(f"Merged detection found {len(merged)} sources: "
                           f"{[r.datasource for r in merged]}")
                return merged
        
        # Return rule-based results even if low confidence
        return rule_results

    def _merge_results(
        self,
        rule_results: List[DataSourceRelevance],
        llm_results: List[DataSourceRelevance]
    ) -> List[DataSourceRelevance]:
        """
        Merge results from rule-based and LLM detection.
        
        Takes the higher confidence for each source and combines reasoning.
        """
        merged = {}
        
        # Add rule-based results
        for r in rule_results:
            merged[r.datasource] = r
        
        # Merge LLM results (prefer higher confidence)
        for r in llm_results:
            if r.datasource in merged:
                existing = merged[r.datasource]
                if r.confidence > existing.confidence:
                    # Keep LLM result but add rule-based reasoning
                    merged[r.datasource] = DataSourceRelevance(
                        datasource=r.datasource,
                        confidence=r.confidence,
                        reasoning=f"{r.reasoning} (also: {existing.reasoning})",
                        suggested_approach=r.suggested_approach or existing.suggested_approach
                    )
            else:
                merged[r.datasource] = r
        
        # Sort by confidence and return
        result = list(merged.values())
        result.sort(key=lambda x: x.confidence, reverse=True)
        return result

    def is_multi_source_query(self, query: str) -> bool:
        """
        Quickly determine if a query might need multiple sources.
        
        Looks for patterns that suggest cross-source queries.
        
        Args:
            query: The query to analyze
            
        Returns:
            True if query likely needs multiple sources
        """
        query_lower = query.lower()
        
        # Patterns that suggest multi-source queries
        multi_source_patterns = [
            r'\band\b.*\bfrom\b',        # "X and Y from Z"
            r'\bcombine\b',               # "combine data from"
            r'\bcompare\b',               # "compare X with Y"
            r'\bacross\b',                # "across all sources"
            r'\bboth\b',                  # "from both"
            r'\ball\s+(?:my|our|the)\b',  # "all my data"
            r'\bsummary\b.*\beverything\b',  # "summary of everything"
            r'\bdashboard\b',             # dashboard queries
            r'\boverview\b',              # overview queries
        ]
        
        for pattern in multi_source_patterns:
            if re.search(pattern, query_lower):
                return True
        
        # Count distinct source keywords mentioned
        source_keywords_found = 0
        for source, patterns in self._keyword_patterns.items():
            for kw in patterns["keywords"][:5]:  # Check top 5 keywords
                if kw.lower() in query_lower:
                    source_keywords_found += 1
                    break
        
        # If multiple sources mentioned, it's likely multi-source
        return source_keywords_found >= 2


# Create global instance for import
source_detector = SourceDetector()







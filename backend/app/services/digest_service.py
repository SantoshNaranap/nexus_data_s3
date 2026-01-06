"""
Digest Service for "What You Missed" Feature.

This service generates a personalized digest of updates across all connected
data sources since the user's last login.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mcp_service import mcp_service
from app.services.credential_service import credential_service
from app.services.result_synthesizer import result_synthesizer
from app.models.agent import SourceQueryResult

logger = logging.getLogger(__name__)


class DigestService:
    """Service for generating personalized digests of missed updates."""

    # Query templates for each datasource type
    QUERY_TEMPLATES = {
        "jira": "Show me all JIRA issues that were created or updated since {since_date}. Include the issue key, summary, status, assignee, and what changed.",
        "slack": "Show me Slack messages and mentions since {since_date}. Include channel names, message previews, and who sent them.",
        "mysql": "Show me recent database activity or changes since {since_date}.",
        "s3": "List any S3 files or objects that were modified since {since_date}.",
        "google_workspace": "Show me emails received and calendar events since {since_date}.",
        "shopify": "Show me Shopify orders and activity since {since_date}.",
        "github": "Show me GitHub activity including issues, pull requests, and commits since {since_date}.",
    }

    # Known datasource types that can have credentials
    KNOWN_DATASOURCES = ["jira", "slack", "mysql", "s3", "google_workspace", "shopify", "github"]

    async def get_configured_sources(
        self,
        db: AsyncSession,
        user_id: str
    ) -> List[str]:
        """Get list of datasources the user has configured credentials for."""
        configured = []
        for datasource in self.KNOWN_DATASOURCES:
            try:
                # has_credentials signature: (datasource, db, user_id, session_id)
                has_creds = await credential_service.has_credentials(datasource, db, user_id)
                if has_creds:
                    configured.append(datasource)
            except Exception as e:
                logger.debug(f"Error checking credentials for {datasource}: {e}")
        return configured

    def _format_since_date(self, since: datetime) -> str:
        """Format a datetime for use in queries."""
        return since.strftime("%Y-%m-%d %H:%M:%S")

    def _get_query_for_source(self, datasource: str, since: datetime) -> str:
        """Generate a time-filtered query for a specific datasource."""
        since_str = self._format_since_date(since)
        template = self.QUERY_TEMPLATES.get(
            datasource,
            f"Show me any updates or changes since {since_str}."
        )
        return template.format(since_date=since_str)

    async def _query_single_source(
        self,
        datasource: str,
        query: str,
        user_id: str,
        db: AsyncSession,
    ) -> SourceQueryResult:
        """Query a single datasource and return results."""
        start_time = datetime.utcnow()

        try:
            logger.info(f"Querying {datasource} for digest: {query[:50]}...")

            # Get tools for this datasource
            tools = await mcp_service.get_cached_tools(datasource)

            if not tools:
                return SourceQueryResult(
                    datasource=datasource,
                    success=False,
                    error="No tools available for this datasource",
                    tools_called=[],
                    timestamp=datetime.utcnow(),
                )

            # Execute query using the chat service pattern
            # For now, use a simplified direct tool call approach
            from app.services.chat_service import chat_service

            # Build a simple message list for the query
            messages = [{"role": "user", "content": query}]

            # Get system prompt for this datasource
            system_prompt = chat_service._create_system_prompt(datasource)

            # Call Claude to execute the query
            response, tool_calls = await chat_service._call_claude(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                datasource=datasource,
                user_id=user_id,
                db=db,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return SourceQueryResult(
                datasource=datasource,
                success=True,
                data={"response": response},
                summary=response[:500] if response else "No updates found",
                tools_called=[tc.get("tool", "unknown") for tc in tool_calls] if tool_calls else [],
                execution_time_ms=execution_time,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Error querying {datasource} for digest: {e}")
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return SourceQueryResult(
                datasource=datasource,
                success=False,
                error=str(e),
                tools_called=[],
                execution_time_ms=execution_time,
                timestamp=datetime.utcnow(),
            )

    async def generate_digest(
        self,
        db: AsyncSession,
        user_id: str,
        since: Optional[datetime] = None,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a digest of updates across all connected sources.

        Args:
            db: Database session
            user_id: User ID to generate digest for
            since: Timestamp to query from (defaults to previous_login)
            sources: Optional list of specific sources to query

        Returns:
            Dict containing:
            - since: The timestamp queried from
            - results: List of SourceQueryResult per source
            - summary: Synthesized summary of all updates
            - successful_sources: List of sources that succeeded
            - failed_sources: List of sources that failed
        """
        start_time = datetime.utcnow()

        # Get configured sources if not specified
        if sources is None:
            sources = await self.get_configured_sources(db, user_id)

        if not sources:
            return {
                "since": since.isoformat() if since else None,
                "results": [],
                "summary": "No data sources configured. Add your credentials in Settings to see updates.",
                "successful_sources": [],
                "failed_sources": [],
                "total_time_ms": 0,
            }

        # Default to 24 hours ago if no since timestamp
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        logger.info(f"Generating digest for user {user_id} since {since} from sources: {sources}")

        # Build queries for each source
        source_queries = {
            source: self._get_query_for_source(source, since)
            for source in sources
        }

        # Execute queries with limited concurrency (max 2 at a time to avoid overwhelming system)
        MAX_CONCURRENT_SOURCES = 2
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SOURCES)

        async def query_with_semaphore(source: str, query: str):
            async with semaphore:
                return await self._query_single_source(source, query, user_id, db)

        tasks = [
            query_with_semaphore(source, query)
            for source, query in source_queries.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results = []
        successful_sources = []
        failed_sources = []

        for i, result in enumerate(results):
            source = sources[i]

            if isinstance(result, Exception):
                # Handle exception from gather
                processed_results.append(SourceQueryResult(
                    datasource=source,
                    success=False,
                    error=str(result),
                    tools_called=[],
                    timestamp=datetime.utcnow(),
                ))
                failed_sources.append(source)
            elif isinstance(result, SourceQueryResult):
                processed_results.append(result)
                if result.success:
                    successful_sources.append(source)
                else:
                    failed_sources.append(source)

        # Synthesize results into a summary
        summary = await self._synthesize_digest(processed_results, since)

        total_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "since": since.isoformat(),
            "results": [r.dict() if hasattr(r, 'dict') else r.__dict__ for r in processed_results],
            "summary": summary,
            "successful_sources": successful_sources,
            "failed_sources": failed_sources,
            "total_time_ms": total_time,
        }

    async def _synthesize_digest(
        self,
        results: List[SourceQueryResult],
        since: datetime,
    ) -> str:
        """Synthesize results into a formatted digest summary."""
        # Filter to successful results with data
        successful_results = [r for r in results if r.success and r.data]

        if not successful_results:
            return "No updates found from your connected sources."

        # Build context for synthesis
        synthesis_prompt = f"""Create a concise digest summary of updates since {since.strftime('%B %d, %Y at %I:%M %p')}.

Group updates by source and highlight the most important items.

FORMATTING RULES:
- NO emojis anywhere in the response
- Use markdown headers (##, ###) for sections
- Use bullet points for individual items
- Keep it scannable and professional
- Prioritize actionable items

Source Data:
"""

        for result in successful_results:
            synthesis_prompt += f"\n\n### {result.datasource.upper()}\n"
            if result.data and isinstance(result.data, dict):
                response = result.data.get("response", result.summary or "No details")
                synthesis_prompt += response[:2000]  # Limit size
            elif result.summary:
                synthesis_prompt += result.summary

        # Use the result synthesizer to create the summary
        try:
            summary = await result_synthesizer._call_synthesis_llm(
                synthesis_prompt,
                "Create a digest summary"
            )
            return summary
        except Exception as e:
            logger.error(f"Error synthesizing digest: {e}")
            # Fallback to simple concatenation
            parts = []
            for r in successful_results:
                parts.append(f"## {r.datasource.upper()}\n{r.summary or 'Updates available'}")
            return "\n\n".join(parts)


# Export singleton instance
digest_service = DigestService()

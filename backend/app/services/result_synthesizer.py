"""
Result Synthesizer Service for Multi-Source Agent Orchestration.

This module takes results from multiple data source queries and synthesizes
them into a coherent, unified response using an LLM. It handles:
1. Combining data from heterogeneous sources
2. Resolving conflicts or inconsistencies
3. Generating natural language summaries
4. Creating structured cross-source insights
"""

import logging
import json
from typing import List, Optional

from anthropic import APIError, APIConnectionError, RateLimitError

from app.services.claude_client import claude_client
from app.models.agent import SourceQueryResult, AgentPlan

# Configure logging
logger = logging.getLogger(__name__)


class ResultSynthesizer:
    """
    Synthesizes results from multiple data sources into unified responses.
    
    Uses Claude to intelligently combine and summarize data from different
    sources, handling the complexity of heterogeneous data formats.
    """

    def __init__(self):
        """Initialize the synthesizer with LLM client."""
        # Use centralized Claude client
        self.client = claude_client.client

        # Maximum characters to include from each source result
        self.max_result_chars = 3000

        # System prompt for synthesis
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt for result synthesis.
        
        This prompt instructs Claude on how to combine multi-source results.
        """
        return """You are an expert data analyst that synthesizes information from multiple data sources.

Your task is to:
1. Analyze results from multiple data sources
2. Identify connections and patterns across sources
3. Resolve any conflicts or inconsistencies
4. Generate a clear, unified response

Guidelines:
- Present information in a logical, organized manner
- Use tables, lists, and markdown formatting for clarity
- Highlight key insights that come from combining sources
- Be explicit about which source each piece of information comes from
- If sources conflict, explain the discrepancy
- Provide actionable insights when possible
- Keep the response focused and relevant to the original query

CRITICAL FORMATTING RULES - MANDATORY:
- ABSOLUTELY NO EMOJIS - Never use emoji characters like 🚀📊🔴🟡🟢🎯📋💡 etc.
- This is a strict requirement - zero tolerance for emojis
- Use plain text headers: ## Main Header, ### Subheader
- Use bullet points (-) and numbered lists (1. 2. 3.)
- Use markdown tables for data presentation
- Use **bold** and *italic* for emphasis - never emoji icons
- Format like a professional business report - clean and minimal

Response Format:
- Start with a brief summary answering the user's question
- Then provide details organized by topic or source
- Use tables for issue lists, metrics, or comparisons
- End with key insights or recommendations if appropriate"""

    def _truncate_result(self, result: str, max_chars: int) -> str:
        """
        Truncate a result to fit within character limits.
        
        Tries to truncate intelligently at word/sentence boundaries.
        """
        if len(result) <= max_chars:
            return result
        
        # Find a good truncation point
        truncated = result[:max_chars]
        
        # Try to truncate at sentence boundary
        last_period = truncated.rfind('.')
        if last_period > max_chars * 0.8:  # If period is in last 20%
            truncated = truncated[:last_period + 1]
        else:
            # Truncate at word boundary
            last_space = truncated.rfind(' ')
            if last_space > 0:
                truncated = truncated[:last_space]
        
        return truncated + "... [truncated]"

    def _format_source_results(
        self,
        results: List[SourceQueryResult]
    ) -> str:
        """
        Format source results for inclusion in the synthesis prompt.
        
        Creates a structured representation of all source data.
        """
        formatted_parts = []
        
        for result in results:
            # Start with source header
            header = f"\n### Source: {result.datasource.upper()}"
            
            if result.success:
                # Format successful result
                status = "SUCCESS"
                
                # Get the data content
                data_content = ""
                if result.data:
                    if isinstance(result.data, str):
                        data_content = self._truncate_result(result.data, self.max_result_chars)
                    else:
                        try:
                            data_content = self._truncate_result(
                                json.dumps(result.data, indent=2, default=str),
                                self.max_result_chars
                            )
                        except (TypeError, ValueError):
                            data_content = str(result.data)[:self.max_result_chars]
                
                # Add summary if available
                summary = f"\nSummary: {result.summary}" if result.summary else ""
                
                # Add tools called
                tools = f"\nTools used: {', '.join(result.tools_called)}" if result.tools_called else ""
                
                formatted_parts.append(
                    f"{header}\n{status}{summary}{tools}\n\nData:\n{data_content}"
                )
            else:
                # Format failed result
                status = "FAILED"
                error = f"\nError: {result.error}" if result.error else ""
                
                formatted_parts.append(f"{header}\n{status}{error}")
        
        return "\n\n---\n".join(formatted_parts)

    async def synthesize(
        self,
        query: str,
        results: List[SourceQueryResult],
        plan: Optional[AgentPlan] = None
    ) -> str:
        """
        Synthesize results from multiple sources into a unified response.
        
        Args:
            query: The original user query
            results: List of results from each source
            plan: Optional execution plan for context
            
        Returns:
            Synthesized natural language response
        """
        # Handle edge cases
        if not results:
            return "I couldn't retrieve any data from the requested sources. Please try again or check your credentials."
        
        # Check if all sources failed
        successful_results = [r for r in results if r.success]
        if not successful_results:
            error_summary = "\n".join([
                f"- {r.datasource}: {r.error}" for r in results
            ])
            return f"All data sources encountered errors:\n{error_summary}\n\nPlease check your credentials and try again."
        
        # Format results for synthesis
        formatted_results = self._format_source_results(results)
        
        # Build context about what was queried
        sources_queried = [r.datasource for r in results]
        sources_succeeded = [r.datasource for r in successful_results]
        sources_failed = [r.datasource for r in results if not r.success]
        
        context = f"""
Sources queried: {', '.join(sources_queried)}
Successful: {', '.join(sources_succeeded)}
Failed: {', '.join(sources_failed) if sources_failed else 'None'}
"""
        
        # Add plan context if available
        if plan:
            context += f"\nPlan reasoning: {plan.plan_reasoning}"
        
        # Build synthesis prompt
        synthesis_prompt = f"""USER QUERY: "{query}"

QUERY CONTEXT:
{context}

DATA FROM SOURCES:
{formatted_results}

---

Based on the data above, provide a comprehensive response to the user's query.
Synthesize information from all successful sources and highlight any cross-source insights."""

        logger.info(f"Synthesizing results from {len(successful_results)} sources")
        
        try:
            # Use Sonnet for high-quality synthesis
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=self._system_prompt,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )
            
            synthesized = response.content[0].text
            
            # Add source attribution footer if multiple sources
            if len(sources_succeeded) > 1:
                synthesized += f"\n\n---\n*Data synthesized from: {', '.join(sources_succeeded)}*"
            
            return synthesized
            
        except (APIError, APIConnectionError, RateLimitError) as e:
            logger.error(f"Synthesis API error: {e}")
            # Fallback to simple concatenation
            return self._fallback_synthesis(query, results)

    def _fallback_synthesis(
        self,
        query: str,
        results: List[SourceQueryResult]
    ) -> str:
        """
        Fallback synthesis when LLM fails.
        
        Provides a basic concatenation of results without intelligent merging.
        """
        parts = [f"## Results for: {query}\n"]
        
        for result in results:
            source_header = f"\n### From {result.datasource.upper()}\n"
            
            if result.success:
                if result.summary:
                    content = result.summary
                elif result.data:
                    content = str(result.data)[:1000]
                else:
                    content = "Query completed successfully."
            else:
                content = f"Error: {result.error or 'Unknown error'}"
            
            parts.append(f"{source_header}{content}")
        
        return "\n".join(parts)

    async def synthesize_stream(
        self,
        query: str,
        results: List[SourceQueryResult],
        plan: Optional[AgentPlan] = None
    ):
        """
        Stream the synthesis response for real-time display.
        
        Yields chunks of the synthesized response as they're generated.
        
        Args:
            query: The original user query
            results: List of results from each source
            plan: Optional execution plan for context
            
        Yields:
            String chunks of the synthesized response
        """
        # Handle edge cases
        if not results:
            yield "I couldn't retrieve any data from the requested sources."
            return
        
        successful_results = [r for r in results if r.success]
        if not successful_results:
            yield "All data sources encountered errors. Please check credentials and try again."
            return
        
        # Format results
        formatted_results = self._format_source_results(results)
        
        sources_queried = [r.datasource for r in results]
        sources_succeeded = [r.datasource for r in successful_results]
        
        context = f"Sources: {', '.join(sources_queried)}"
        
        synthesis_prompt = f"""USER QUERY: "{query}"

{context}

DATA FROM SOURCES:
{formatted_results}

---

Synthesize a comprehensive response to the user's query."""

        try:
            # Stream the synthesis
            stream = self.client.messages.stream(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=self._system_prompt,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )
            
            with stream as event_stream:
                for event in event_stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield event.delta.text
            
            # Add attribution footer
            if len(sources_succeeded) > 1:
                yield f"\n\n---\n*Data from: {', '.join(sources_succeeded)}*"
                
        except (APIError, APIConnectionError, RateLimitError) as e:
            logger.error(f"Stream synthesis API error: {e}")
            yield self._fallback_synthesis(query, results)

    def generate_quick_summary(
        self,
        results: List[SourceQueryResult]
    ) -> str:
        """
        Generate a quick summary without LLM call.
        
        Useful for immediate feedback while full synthesis is processing.
        
        Args:
            results: List of source query results
            
        Returns:
            Quick summary string
        """
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        parts = []
        
        if successful:
            sources = [r.datasource for r in successful]
            parts.append(f"Retrieved data from: {', '.join(sources)}")

        if failed:
            sources = [r.datasource for r in failed]
            parts.append(f"Failed to query: {', '.join(sources)}")
        
        return " | ".join(parts)


# Create global instance for import
result_synthesizer = ResultSynthesizer()








/**
 * Agent API Service for Multi-Source Queries
 *
 * This service provides frontend access to the agent orchestration system,
 * enabling multi-source queries with real-time streaming updates.
 */

import { API_BASE_URL } from './api';

/**
 * Data source relevance information from the source detector
 */
export interface DataSourceRelevance {
  datasource: string;         // Source identifier (e.g., "jira", "s3")
  confidence: number;         // Confidence score 0-1
  reasoning: string;          // Why this source is relevant
  suggested_approach?: string; // How to query this source
}

/**
 * Result from a single data source query
 */
export interface SourceQueryResult {
  datasource: string;         // Source that was queried
  success: boolean;           // Whether query succeeded
  data?: any;                 // Query result data
  summary?: string;           // Brief summary of results
  error?: string;             // Error message if failed
  tools_called: string[];     // Tools used during query
  execution_time_ms?: number; // Time taken in milliseconds
  timestamp: string;          // When result was generated
}

/**
 * Execution plan created by the agent
 */
export interface AgentPlan {
  original_query: string;                  // The user's query
  relevant_sources: DataSourceRelevance[]; // All detected sources
  sources_to_query: string[];              // Sources that will be queried
  execution_mode: string;                  // "parallel" or "sequential"
  plan_reasoning: string;                  // Why this plan was chosen
  estimated_time_ms?: number;              // Estimated execution time
}

/**
 * Request model for multi-source queries
 */
export interface MultiSourceRequest {
  query: string;                   // Natural language query
  sources?: string[];              // Optional: specific sources to query
  session_id?: string;             // Optional: session for context
  confidence_threshold?: number;   // Minimum confidence (default 0.5)
  max_sources?: number;            // Maximum sources (default 3)
  include_plan?: boolean;          // Include execution plan (default true)
}

/**
 * Response model for multi-source queries
 */
export interface MultiSourceResponse {
  response: string;                    // Synthesized response
  session_id: string;                  // Session ID
  status: string;                      // completed, partial, failed
  plan?: AgentPlan;                    // Execution plan
  source_results: SourceQueryResult[]; // Individual source results
  successful_sources: string[];        // Sources that succeeded
  failed_sources: string[];            // Sources that failed
  total_execution_time_ms?: number;    // Total time taken
  timestamp: string;                   // Response timestamp
}

/**
 * Stream event from multi-source query execution
 */
export interface AgentStreamEvent {
  event_type: string;    // Event type
  data: any;             // Event-specific data
  message?: string;      // Human-readable message
  timestamp: string;     // Event timestamp
}

/**
 * Detection result for multi-source analysis
 */
export interface MultiSourceDetection {
  is_multi_source: boolean;        // Whether multi-source is recommended
  suggested_sources: string[];     // Suggested sources to query
  sources_with_confidence: Array<{
    datasource: string;
    confidence: number;
  }>;
  reasoning: string;               // Explanation
}

/**
 * Agent API for multi-source queries
 */
export const agentApi = {
  /**
   * Execute a multi-source query
   * 
   * @param request - The multi-source query request
   * @returns MultiSourceResponse with synthesized results
   * 
   * @example
   * const response = await agentApi.query({
   *   query: "What are my latest JIRA tasks and recent emails?",
   *   max_sources: 2,
   *   include_plan: true
   * });
   */
  query: async (request: MultiSourceRequest): Promise<MultiSourceResponse> => {
    const response = await fetch(`${API_BASE_URL}/api/agent/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include', // Include cookies for auth
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Agent query failed: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Execute a multi-source query with streaming progress updates
   * 
   * @param request - The multi-source query request
   * @param callbacks - Callbacks for different event types
   * 
   * @example
   * await agentApi.queryStream(
   *   { query: "Compare JIRA tasks with emails" },
   *   {
   *     onPlanComplete: (sources) => console.log("Will query:", sources),
   *     onSourceComplete: (source, success) => updateUI(source, success),
   *     onSynthesisChunk: (chunk) => appendToResponse(chunk),
   *     onDone: (result) => showComplete(result),
   *     onError: (error) => showError(error),
   *   }
   * );
   */
  queryStream: async (
    request: MultiSourceRequest,
    callbacks: {
      onStarted?: (sessionId: string) => void;
      onPlanning?: () => void;
      onPlanComplete?: (sources: string[], reasoning: string) => void;
      onSourceStart?: (datasource: string) => void;
      onSourceComplete?: (datasource: string, success: boolean, error?: string) => void;
      onSynthesizing?: () => void;
      onSynthesisChunk?: (chunk: string) => void;
      onDone?: (result: { successful_sources: string[]; failed_sources: string[]; total_time_ms: number }) => void;
      onError?: (error: string) => void;
      onEvent?: (event: AgentStreamEvent) => void; // Raw event handler
    }
  ): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/agent/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Agent stream failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('No response body');
    }

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: AgentStreamEvent = JSON.parse(line.slice(6));

              // Call raw event handler if provided
              callbacks.onEvent?.(event);

              // Call specific handlers based on event type
              switch (event.event_type) {
                case 'started':
                  callbacks.onStarted?.(event.data.session_id);
                  break;
                case 'planning':
                  callbacks.onPlanning?.();
                  break;
                case 'plan_complete':
                  callbacks.onPlanComplete?.(event.data.sources, event.data.reasoning);
                  break;
                case 'source_start':
                  callbacks.onSourceStart?.(event.data.datasource);
                  break;
                case 'source_complete':
                  callbacks.onSourceComplete?.(
                    event.data.datasource,
                    event.data.success,
                    event.data.error
                  );
                  break;
                case 'synthesizing':
                  callbacks.onSynthesizing?.();
                  break;
                case 'synthesis_chunk':
                  callbacks.onSynthesisChunk?.(event.data.content);
                  break;
                case 'done':
                  callbacks.onDone?.(event.data);
                  break;
                case 'error':
                  callbacks.onError?.(event.data.error || event.message || 'Unknown error');
                  break;
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE event:', line, parseError);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  /**
   * Get source suggestions for a query without executing it
   * 
   * @param query - The natural language query
   * @param maxSuggestions - Maximum number of suggestions (default 5)
   * @returns List of relevant sources with confidence scores
   * 
   * @example
   * const suggestions = await agentApi.suggest("Show me open bugs", 3);
   * // Returns: [{ datasource: "jira", confidence: 0.95, reasoning: "..." }]
   */
  suggest: async (
    query: string,
    maxSuggestions: number = 5
  ): Promise<DataSourceRelevance[]> => {
    const response = await fetch(`${API_BASE_URL}/api/agent/suggest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ query, max_suggestions: maxSuggestions }),
    });

    if (!response.ok) {
      throw new Error(`Suggest failed: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Detect if a query should use multi-source processing
   * 
   * @param query - The natural language query
   * @returns Detection result with recommendation
   * 
   * @example
   * const detection = await agentApi.detect("Compare JIRA with emails");
   * if (detection.is_multi_source) {
   *   // Use multi-source query
   * } else {
   *   // Use single-source query
   * }
   */
  detect: async (query: string): Promise<MultiSourceDetection> => {
    const response = await fetch(`${API_BASE_URL}/api/agent/detect`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      throw new Error(`Detection failed: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Get list of available data sources
   * 
   * @returns List of available sources with metadata
   */
  getSources: async (): Promise<Array<{
    id: string;
    name: string;
    description: string;
    enabled: boolean;
  }>> => {
    const response = await fetch(`${API_BASE_URL}/api/agent/sources`, {
      method: 'GET',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Get sources failed: ${response.statusText}`);
    }

    return response.json();
  },
};

export default agentApi;







/**
 * SSE (Server-Sent Events) Parser Utility
 *
 * Provides shared functionality for parsing SSE streams from the backend.
 * Used by both chatApi and agentApi for consistent stream handling.
 */

export interface SSEEvent<T = unknown> {
  type: string;
  data: T;
}

export interface SSEParserCallbacks<T = unknown> {
  onEvent: (event: SSEEvent<T>) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

/**
 * Parse SSE stream from a fetch response
 *
 * @param response - Fetch response with body stream
 * @param callbacks - Event handlers for parsed events
 */
export async function parseSSEStream<T = unknown>(
  response: Response,
  callbacks: SSEParserCallbacks<T>
): Promise<void> {
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    throw new Error('No response body');
  }

  // Buffer for incomplete lines split across chunk boundaries
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      // Append new data to any leftover buffer from the previous chunk
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');

      // The last element may be an incomplete line — keep it in the buffer
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            callbacks.onEvent({ type: data.type || data.event_type, data });
          } catch (parseError) {
            console.debug('Skipping malformed SSE line:', line);
          }
        }
      }
    }
    callbacks.onComplete?.();
  } catch (error) {
    callbacks.onError?.(error instanceof Error ? error : new Error(String(error)));
  } finally {
    reader.releaseLock();
  }
}

/**
 * Create a streaming fetch request with SSE parsing
 *
 * @param url - The URL to fetch
 * @param options - Fetch options (method, body, etc.)
 * @param callbacks - Event handlers for parsed events
 */
export async function fetchSSE<T = unknown>(
  url: string,
  options: RequestInit,
  callbacks: SSEParserCallbacks<T>
): Promise<void> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  await parseSSEStream(response, callbacks);
}

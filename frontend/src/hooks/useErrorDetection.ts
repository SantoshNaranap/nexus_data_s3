import { useCallback } from 'react';

/**
 * Error patterns that indicate a potential error in chat responses.
 * These patterns detect various types of failures that warrant investigation.
 */
const ERROR_PATTERNS = [
  /sorry.*unable/i,
  /unable to (search|retrieve|connect|find|access)/i,
  /failed to/i,
  /couldn't (retrieve|find|search|connect|access)/i,
  /error occurred/i,
  /timed out/i,
  /connection failed/i,
  /authentication failed/i,
  /access denied/i,
  /service.*unavailable/i,
  /^Error:/,
  /unauthorized/i,
  /token expired/i,
  /permission denied/i,
  /rate limit/i,
  /circuit breaker/i,
  /no results found/i,
  /could not connect/i,
  /network error/i,
  /internal server error/i,
  /bad request/i,
  /forbidden/i,
  /not found.*resource/i,
  /credential.*invalid/i,
  /credential.*missing/i,
  /credential.*expired/i,
  // MCP tool availability errors
  /unknown tool/i,
  /tool.*not (available|found|accessible)/i,
  /tool.*failed to execute/i,
  /functionality.*not.*accessible/i,
  /connector.*unavailable/i,
  /connector.*needs to be (reviewed|reconfigured)/i,
  /not currently accessible/i,
  /no longer accessible/i,
  /cannot (show|retrieve|find|access|answer)/i,
  /I cannot/i,
  /no way to retrieve/i,
  /no data available/i,
  /I apologize.*cannot/i,
];

/**
 * Patterns that indicate false positives - messages that look like errors
 * but are actually informative responses about search results.
 */
const FALSE_POSITIVE_PATTERNS = [
  /no\s+(issues?|results?|data|items?)\s+(found|match|available)\s+(for|in|with)/i,
  /search\s+returned\s+no\s+results/i,
  /there\s+(are|is)\s+no\s+/i,
  /I\s+(could\s+not|couldn't)\s+find\s+any\s+(?!.*error)/i,
  /no\s+matching\s+/i,
  /empty\s+response/i,
];

export interface UseErrorDetectionReturn {
  /**
   * Detect if a message content contains error patterns
   * @param content - The message content to analyze
   * @returns true if an error pattern is detected, false otherwise
   */
  detectError: (content: string) => boolean;

  /**
   * Get the matched error pattern for logging/debugging
   * @param content - The message content to analyze
   * @returns The matched pattern or null if no match
   */
  getMatchedPattern: (content: string) => RegExp | null;
}

/**
 * Hook for detecting errors in chat responses.
 *
 * @example
 * ```tsx
 * const { detectError } = useErrorDetection();
 *
 * if (detectError(message.content)) {
 *   // Trigger error investigation
 * }
 * ```
 */
export function useErrorDetection(): UseErrorDetectionReturn {
  const detectError = useCallback((content: string): boolean => {
    // First check if it's a false positive
    for (const pattern of FALSE_POSITIVE_PATTERNS) {
      if (pattern.test(content)) {
        return false;
      }
    }

    // Then check for actual error patterns
    for (const pattern of ERROR_PATTERNS) {
      if (pattern.test(content)) {
        return true;
      }
    }

    return false;
  }, []);

  const getMatchedPattern = useCallback((content: string): RegExp | null => {
    // First check if it's a false positive
    for (const pattern of FALSE_POSITIVE_PATTERNS) {
      if (pattern.test(content)) {
        return null;
      }
    }

    // Then check for actual error patterns
    for (const pattern of ERROR_PATTERNS) {
      if (pattern.test(content)) {
        return pattern;
      }
    }

    return null;
  }, []);

  return {
    detectError,
    getMatchedPattern,
  };
}

export default useErrorDetection;

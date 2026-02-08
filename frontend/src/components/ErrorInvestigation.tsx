import { useState } from 'react';
import type { ErrorInvestigation } from '../types';

interface ErrorInvestigationPanelProps {
  investigation: ErrorInvestigation;
  isInvestigating?: boolean;
}

/**
 * Severity badge component with color coding
 */
function SeverityBadge({ severity }: { severity: 'critical' | 'warning' | 'info' }) {
  const colors = {
    critical: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
    info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  };

  const icons = {
    critical: (
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
    ),
    warning: (
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
    info: (
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
      </svg>
    ),
  };

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${colors[severity]}`}>
      {icons[severity]}
      {severity}
    </span>
  );
}

/**
 * Category icon based on finding type
 */
function CategoryIcon({ category }: { category: string }) {
  const icons: Record<string, JSX.Element> = {
    credentials: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
      </svg>
    ),
    circuit_breaker: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    connection: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
      </svg>
    ),
    mcp: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
    ),
    error_pattern: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    unknown: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  };

  return icons[category] || icons.unknown;
}

/**
 * Investigating spinner component
 */
function InvestigatingSpinner() {
  return (
    <div className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
      <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-600 border-t-transparent" />
      <div>
        <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
          Detected an error — investigating and attempting auto-fix...
        </span>
        <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">
          Refreshing tokens, resetting circuit breakers, and testing connection
        </p>
      </div>
    </div>
  );
}

/**
 * Error Investigation Panel component.
 *
 * Displays a collapsible panel showing error investigation findings
 * with severity badges, category icons, and recommendations.
 */
export default function ErrorInvestigationPanel({
  investigation,
  isInvestigating = false,
}: ErrorInvestigationPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (isInvestigating) {
    return <InvestigatingSpinner />;
  }

  if (!investigation || investigation.findings.length === 0) {
    return null;
  }

  // Sort findings by severity: critical first, then warning, then info
  const sortedFindings = [...investigation.findings].sort((a, b) => {
    const severityOrder = { critical: 0, warning: 1, info: 2 };
    return severityOrder[a.severity] - severityOrder[b.severity];
  });

  // Check if auto-fix was successful
  const autoFixFinding = sortedFindings.find(f => f.title === 'Auto-fix successful');
  const autoFixFailed = sortedFindings.find(f => f.title === 'Auto-fix failed' || f.title === 'Partial fix applied');

  // Determine panel color: green if fixed, otherwise by highest severity
  const isFixed = !!autoFixFinding;
  const highestSeverity = isFixed ? 'info' : (sortedFindings[0]?.severity || 'info');
  const panelColors = {
    critical: 'border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10',
    warning: 'border-yellow-200 dark:border-yellow-800 bg-yellow-50/50 dark:bg-yellow-900/10',
    info: isFixed
      ? 'border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10'
      : 'border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/10',
  };

  const headerColors = {
    critical: 'text-red-800 dark:text-red-300',
    warning: 'text-yellow-800 dark:text-yellow-300',
    info: isFixed ? 'text-green-800 dark:text-green-300' : 'text-blue-800 dark:text-blue-300',
  };

  return (
    <div className={`mt-3 rounded-lg border ${panelColors[highestSeverity]} overflow-hidden transition-all`}>
      {/* Header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg
            className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''} ${headerColors[highestSeverity]}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <svg className={`w-4 h-4 ${headerColors[highestSeverity]}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span className={`text-sm font-medium ${headerColors[highestSeverity]}`}>
            {isFixed
              ? 'Auto-fix applied — please retry your query'
              : autoFixFailed
                ? `Auto-fix attempted — ${investigation.root_cause || 'manual action needed'}`
                : investigation.root_cause || 'Error Investigation'}
          </span>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {investigation.duration_ms ? `${investigation.duration_ms}ms` : ''}
        </span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4">
          {/* Findings */}
          <div className="space-y-2">
            {sortedFindings.map((finding, index) => (
              <div
                key={index}
                className="flex items-start gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700"
              >
                <div className="flex-shrink-0 mt-0.5 text-gray-400 dark:text-gray-500">
                  <CategoryIcon category={finding.category} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {finding.title}
                    </span>
                    <SeverityBadge severity={finding.severity} />
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    {finding.detail}
                  </p>
                  {finding.suggested_action && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs text-green-700 dark:text-green-400">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                      {finding.suggested_action}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Recommendations */}
          {investigation.recommendations.length > 0 && (
            <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="font-medium">Recommended Actions</span>
              </div>
              <ul className="space-y-1.5">
                {investigation.recommendations.map((rec, index) => (
                  <li key={index} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <svg className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export { InvestigatingSpinner };

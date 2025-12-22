import { useState, useEffect } from 'react'
import { digestApi, DigestResponse, SourceResult } from '../services/api'
import DataSourceIcon from './DataSourceIcon'

interface WhatYouMissedDashboardProps {
  onClose?: () => void
}

// Map datasource IDs to display names
const SOURCE_NAMES: Record<string, string> = {
  'jira': 'JIRA',
  'slack': 'Slack',
  'mysql': 'MySQL',
  's3': 'Amazon S3',
  'google_workspace': 'Google Workspace',
  'shopify': 'Shopify',
  'github': 'GitHub'
}

export default function WhatYouMissedDashboard({ onClose: _onClose }: WhatYouMissedDashboardProps) {
  const [digest, setDigest] = useState<DigestResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [lastLoginInfo, setLastLoginInfo] = useState<{ previous_login: string | null }>({ previous_login: null })

  const fetchDigest = async () => {
    setLoading(true)
    setError(null)
    try {
      const [digestData, loginInfo] = await Promise.all([
        digestApi.getDigest(),
        digestApi.getLastLogin()
      ])
      setDigest(digestData)
      setLastLoginInfo({
        previous_login: loginInfo.previous_login
      })
      // Auto-expand successful sources
      const successfulSources = new Set(
        digestData.results
          .filter(item => item.success)
          .map(item => item.datasource)
      )
      setExpandedSources(successfulSources)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch updates')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDigest()
  }, [])

  const toggleSource = (source: string) => {
    setExpandedSources(prev => {
      const newSet = new Set(prev)
      if (newSet.has(source)) {
        newSet.delete(source)
      } else {
        newSet.add(source)
      }
      return newSet
    })
  }

  const formatDate = (isoString: string | null) => {
    if (!isoString) return 'Unknown'
    const date = new Date(isoString)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    })
  }

  const getTimeSince = (isoString: string | null): string => {
    if (!isoString) return ''
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    const diffDays = Math.floor(diffHours / 24)

    if (diffDays > 0) {
      return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
    } else if (diffHours > 0) {
      return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
    } else {
      return 'recently'
    }
  }

  const getSourceName = (sourceId: string): string => {
    return SOURCE_NAMES[sourceId] || sourceId.charAt(0).toUpperCase() + sourceId.slice(1)
  }

  const getSourceContent = (result: SourceResult): string => {
    if (result.data?.response) {
      return result.data.response
    }
    if (result.summary) {
      return result.summary
    }
    return 'No details available'
  }

  if (loading) {
    return (
      <div className="flex-1 flex flex-col bg-gray-50 dark:bg-gray-900">
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4">
              <svg className="animate-spin w-full h-full text-amber-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
            <p className="text-gray-600 dark:text-gray-400">Loading your updates...</p>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col bg-gray-50 dark:bg-gray-900">
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-red-600 dark:text-red-400 mb-4">{error}</p>
            <button
              onClick={fetchDigest}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    )
  }

  const successCount = digest?.successful_sources?.length || 0
  const failedCount = digest?.failed_sources?.length || 0

  return (
    <div className="flex-1 flex flex-col bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-medium text-gray-900 dark:text-white flex items-center gap-2">
              <svg className="w-6 h-6 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
              What You Missed
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {lastLoginInfo.previous_login ? (
                <>Since: {formatDate(lastLoginInfo.previous_login)} ({getTimeSince(lastLoginInfo.previous_login)})</>
              ) : digest?.since ? (
                <>Since: {formatDate(digest.since)}</>
              ) : (
                'Welcome! Here are your latest updates.'
              )}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {successCount} source{successCount !== 1 ? 's' : ''} queried
              {failedCount > 0 && `, ${failedCount} failed`}
            </span>
            <button
              onClick={fetchDigest}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              title="Refresh"
            >
              <svg className="w-5 h-5 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {!digest || digest.results.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-gray-600 dark:text-gray-400">No data sources configured. Add your credentials in Settings.</p>
          </div>
        ) : (
          <div className="space-y-4 max-w-4xl mx-auto">
            {/* Summary Section */}
            {digest.summary && (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 mb-6">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Summary</h3>
                <div className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap prose dark:prose-invert max-w-none">
                  {digest.summary}
                </div>
              </div>
            )}

            {/* Source Results */}
            {digest.results.map((result: SourceResult) => (
              <div
                key={result.datasource}
                className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
              >
                {/* Source Header */}
                <button
                  onClick={() => toggleSource(result.datasource)}
                  className="w-full px-5 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <DataSourceIcon datasourceId={result.datasource} size={28} />
                    <div className="text-left">
                      <span className="font-medium text-gray-900 dark:text-white">
                        {getSourceName(result.datasource)}
                      </span>
                      {result.success ? (
                        <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full">
                          Success
                        </span>
                      ) : (
                        <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full">
                          Failed
                        </span>
                      )}
                    </div>
                  </div>
                  <svg
                    className={`w-5 h-5 text-gray-400 transition-transform ${expandedSources.has(result.datasource) ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Expanded Content */}
                {expandedSources.has(result.datasource) && (
                  <div className="px-5 pb-4 border-t border-gray-100 dark:border-gray-700">
                    {result.success ? (
                      <div className="text-sm text-gray-700 dark:text-gray-300 py-3 whitespace-pre-wrap">
                        {getSourceContent(result)}
                      </div>
                    ) : (
                      <div className="text-sm text-red-600 dark:text-red-400 py-3">
                        Error: {result.error || 'Unknown error'}
                      </div>
                    )}
                    {result.execution_time_ms && (
                      <div className="text-xs text-gray-400 mt-2">
                        Query time: {Math.round(result.execution_time_ms)}ms
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

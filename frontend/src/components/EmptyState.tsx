import type { DataSource } from '../types'
import DataSourceIcon from './DataSourceIcon'
import { API_BASE_URL } from '../services/api'

interface EmptyStateProps {
  datasource: DataSource
  isConfigured: boolean
  onOpenSettings: () => void
}

const OAUTH_DATASOURCES = ['slack', 'github', 'jira', 'google_workspace']

const EXAMPLE_QUERIES: Record<string, string[]> = {
  mysql: ['"Show me the latest users"', '"How many rows are in the orders table?"'],
  s3: ['"What buckets do I have?"', '"Show me files in my bucket"'],
  google_workspace: ['"Show me my recent Google Docs"', '"List my spreadsheets"', '"What\'s on my calendar today?"'],
  jira: ['"Show me my open issues"', '"What\'s in the backlog?"'],
  github: ['"Show me my repositories"', '"List open pull requests"'],
  slack: ['"What channels do I have?"', '"Show team members"'],
}

export default function EmptyState({ datasource, isConfigured, onOpenSettings }: EmptyStateProps) {
  const examples = EXAMPLE_QUERIES[datasource.id] || ['"Ask me anything..."']
  const isOAuth = OAUTH_DATASOURCES.includes(datasource.id)

  if (!isConfigured) {
    return (
      <div className="text-center mt-16">
        <div className="w-20 h-20 mx-auto bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mb-6">
          <DataSourceIcon datasourceId={datasource.id} size={40} />
        </div>
        <h3 className="text-xl font-normal text-gray-900 dark:text-white mb-2">
          Connect to {datasource.name}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 max-w-md mx-auto mb-8">
          {isOAuth
            ? `Connect your ${datasource.name} account to start querying your data`
            : `Configure your ${datasource.name} credentials to start querying your data`
          }
        </p>
        {isOAuth ? (
          <button
            onClick={() => {
              window.location.href = `${API_BASE_URL}/api/credentials/${datasource.id}/oauth`
            }}
            className="inline-flex items-center px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors shadow-sm hover:shadow-md"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            Connect with {datasource.name}
          </button>
        ) : (
          <button
            onClick={onOpenSettings}
            className="inline-flex items-center px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors shadow-sm hover:shadow-md"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Configure in Settings
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="text-center mt-16">
      <div className="w-20 h-20 mx-auto bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mb-6">
        <svg className="w-10 h-10 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </div>
      <h3 className="text-xl font-normal text-gray-900 dark:text-white mb-2">
        Start chatting with {datasource.name}
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-400 max-w-md mx-auto">
        Ask questions in natural language and I'll help you query your data
      </p>
      <div className="mt-8 inline-block text-left bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 max-w-md">
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-3">Try asking:</p>
        <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
          {examples.map((example, idx) => (
            <p key={idx}>{example}</p>
          ))}
        </div>
      </div>
    </div>
  )
}

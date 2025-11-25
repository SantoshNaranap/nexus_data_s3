import type { DataSource } from '../types'

interface DataSourceSidebarProps {
  datasources: DataSource[]
  selectedDatasource: DataSource | null
  onSelectDatasource: (datasource: DataSource) => void
  isLoading: boolean
}

const dataSourceIcons: Record<string, string> = {
  s3: '🪣',
  mysql: '🐬',
  jira: '📋',
  shopify: '🛍️',
  google_workspace: '📝',
}

export default function DataSourceSidebar({
  datasources,
  selectedDatasource,
  onSelectDatasource,
  isLoading,
}: DataSourceSidebarProps) {
  if (isLoading) {
    return (
      <div className="w-80 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
        <h2 className="text-sm font-medium text-gray-900 dark:text-white mb-4">Data Sources</h2>
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-20 bg-gray-100 dark:bg-gray-800 animate-pulse rounded-lg"
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="w-80 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col transition-colors duration-200">
      <div className="p-6 border-b border-gray-200 dark:border-gray-800">
        <h2 className="text-sm font-medium text-gray-900 dark:text-white mb-1">
          Data Sources
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Select a connector to start
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {datasources.map((datasource) => (
          <button
            key={datasource.id}
            onClick={() => onSelectDatasource(datasource)}
            className={`w-full text-left p-4 rounded-lg transition-all duration-200 ${
              selectedDatasource?.id === datasource.id
                ? 'bg-blue-50 dark:bg-blue-900/20 border-2 border-blue-500'
                : 'border-2 border-transparent hover:bg-gray-50 dark:hover:bg-gray-800'
            } ${!datasource.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            disabled={!datasource.enabled}
          >
            <div className="flex items-start space-x-3">
              <div className="text-2xl flex-shrink-0">
                {dataSourceIcons[datasource.id] || '📊'}
              </div>
              <div className="flex-1 min-w-0">
                <div className={`font-medium text-sm truncate ${
                  selectedDatasource?.id === datasource.id
                    ? 'text-blue-700 dark:text-blue-400'
                    : 'text-gray-900 dark:text-white'
                }`}>
                  {datasource.name}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                  {datasource.description}
                </div>
              </div>
              {selectedDatasource?.id === datasource.id && (
                <svg className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
          </button>
        ))}
      </div>

      <div className="p-4 border-t border-gray-200 dark:border-gray-800">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-500 dark:text-gray-400">Connected sources</span>
          <div className="flex items-center space-x-1.5">
            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            <span className="font-medium text-gray-900 dark:text-white">{datasources.length}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

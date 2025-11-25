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
}

export default function DataSourceSidebar({
  datasources,
  selectedDatasource,
  onSelectDatasource,
  isLoading,
}: DataSourceSidebarProps) {
  if (isLoading) {
    return (
      <div className="w-64 bg-gray-800 border-r border-gray-700 p-4">
        <h2 className="text-lg font-semibold mb-4">Data Sources</h2>
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-16 bg-gray-700 animate-pulse rounded-lg"
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="w-64 bg-gray-800 border-r border-gray-700 p-4 flex flex-col">
      <h2 className="text-lg font-semibold mb-4">Data Sources</h2>

      <div className="space-y-2 flex-1 overflow-y-auto">
        {datasources.map((datasource) => (
          <button
            key={datasource.id}
            onClick={() => onSelectDatasource(datasource)}
            className={`w-full text-left p-3 rounded-lg transition-colors ${
              selectedDatasource?.id === datasource.id
                ? 'bg-blue-600 hover:bg-blue-700'
                : 'bg-gray-700 hover:bg-gray-600'
            } ${!datasource.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            disabled={!datasource.enabled}
          >
            <div className="flex items-start">
              <div className="text-2xl mr-3">
                {dataSourceIcons[datasource.id] || '📊'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{datasource.name}</div>
                <div className="text-xs text-gray-400 mt-1 line-clamp-2">
                  {datasource.description}
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-gray-700 text-xs text-gray-400">
        <p>Connected to {datasources.length} data sources</p>
      </div>
    </div>
  )
}

import type { DataSource } from '../types'
import DataSourceIcon from './DataSourceIcon'

// Special "What You Missed" datasource for digest view
export const DIGEST_DATASOURCE: DataSource = {
  id: 'what_you_missed',
  name: 'What You Missed',
  description: 'Updates since your last login',
  icon: 'digest',
  enabled: true,
}

// Special "All Sources" datasource for multi-source queries
export const ALL_SOURCES_DATASOURCE: DataSource = {
  id: 'all_sources',
  name: 'All Sources',
  description: 'Query across all your connected data sources at once',
  icon: 'all',
  enabled: true,
}

interface DataSourceSidebarProps {
  datasources: DataSource[]
  selectedDatasource: DataSource | null
  onSelectDatasource: (datasource: DataSource) => void
  onOpenSettings: () => void
  configuredDatasources: Set<string>
  isLoading: boolean
}

export default function DataSourceSidebar({
  datasources,
  selectedDatasource,
  onSelectDatasource,
  onOpenSettings,
  configuredDatasources,
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
        {/* What You Missed - digest view at the very top */}
        {configuredDatasources.size >= 1 && (
          <>
            <button
              onClick={() => onSelectDatasource(DIGEST_DATASOURCE)}
              className={`w-full text-left p-4 rounded-lg transition-all duration-200 ${
                selectedDatasource?.id === 'what_you_missed'
                  ? 'bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 border-2 border-amber-500'
                  : 'border-2 border-transparent hover:bg-gradient-to-r hover:from-amber-50/50 hover:to-orange-50/50 dark:hover:from-amber-900/10 dark:hover:to-orange-900/10'
              }`}
            >
              <div className="flex items-start space-x-3">
                <div className="flex-shrink-0">
                  <div className="w-7 h-7 bg-gradient-to-br from-amber-500 to-orange-500 rounded-lg flex items-center justify-center">
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                    </svg>
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className={`font-medium text-sm truncate ${
                      selectedDatasource?.id === 'what_you_missed'
                        ? 'text-amber-700 dark:text-amber-400'
                        : 'text-gray-900 dark:text-white'
                    }`}>
                      What You Missed
                    </div>
                    <span className="px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded">
                      NEW
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                    Updates since your last login
                  </div>
                </div>
                {selectedDatasource?.id === 'what_you_missed' && (
                  <svg className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
            </button>
            <div className="border-t border-gray-200 dark:border-gray-700 my-2"></div>
          </>
        )}

        {/* All Sources option - enabled when 2+ sources are configured */}
        {configuredDatasources.size >= 2 && (
          <>
            <button
              onClick={() => onSelectDatasource(ALL_SOURCES_DATASOURCE)}
              className={`w-full text-left p-4 rounded-lg transition-all duration-200 ${
                selectedDatasource?.id === 'all_sources'
                  ? 'bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/20 dark:to-blue-900/20 border-2 border-purple-500'
                  : 'border-2 border-transparent hover:bg-gradient-to-r hover:from-purple-50/50 hover:to-blue-50/50 dark:hover:from-purple-900/10 dark:hover:to-blue-900/10'
              }`}
            >
              <div className="flex items-start space-x-3">
                <div className="flex-shrink-0">
                  <div className="w-7 h-7 bg-gradient-to-br from-purple-500 to-blue-500 rounded-lg flex items-center justify-center">
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                    </svg>
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className={`font-medium text-sm truncate ${
                      selectedDatasource?.id === 'all_sources'
                        ? 'text-purple-700 dark:text-purple-400'
                        : 'text-gray-900 dark:text-white'
                    }`}>
                      All Sources
                    </div>
                    <span className="px-1.5 py-0.5 text-[10px] font-medium bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded">
                      {configuredDatasources.size}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                    Query across all connected sources
                  </div>
                </div>
                {selectedDatasource?.id === 'all_sources' && (
                  <svg className="w-5 h-5 text-purple-600 dark:text-purple-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
            </button>
            <div className="border-t border-gray-200 dark:border-gray-700 my-2"></div>
          </>
        )}

        {/* Individual datasources */}
        {datasources.map((datasource) => {
          const isConfigured = configuredDatasources.has(datasource.id)

          return (
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
                <div className="flex-shrink-0">
                  <DataSourceIcon datasourceId={datasource.id} size={28} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className={`font-medium text-sm truncate ${
                      selectedDatasource?.id === datasource.id
                        ? 'text-blue-700 dark:text-blue-400'
                        : 'text-gray-900 dark:text-white'
                    }`}>
                      {datasource.name}
                    </div>
                    {isConfigured && (
                      <div className="flex-shrink-0">
                        <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                      </div>
                    )}
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
          )
        })}
      </div>

      <div className="p-4 border-t border-gray-200 dark:border-gray-800 space-y-3">
        {/* Settings Button */}
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center justify-center space-x-2 px-4 py-3 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg transition-all duration-200"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span className="font-medium text-sm">Settings</span>
        </button>

        {/* Connection Status */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-500 dark:text-gray-400">Configured</span>
          <div className="flex items-center space-x-1.5">
            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            <span className="font-medium text-gray-900 dark:text-white">
              {configuredDatasources.size}/{datasources.length}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

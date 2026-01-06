import type { DataSource } from '../types'
import DataSourceIcon from './DataSourceIcon'

interface ChatHeaderProps {
  datasource: DataSource
  sessionId: string | null
  showAgentPanel: boolean
  hasMessages: boolean
  isStreaming: boolean
  onToggleAgentPanel: () => void
  onNewConversation: () => void
}

export default function ChatHeader({
  datasource,
  sessionId,
  showAgentPanel,
  hasMessages,
  isStreaming,
  onToggleAgentPanel,
  onNewConversation,
}: ChatHeaderProps) {
  return (
    <div className="flex-shrink-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4 transition-colors duration-200">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <DataSourceIcon datasourceId={datasource.id} size={32} className="text-gray-700 dark:text-gray-300" />
          <div>
            <h2 className="font-medium text-gray-900 dark:text-white">{datasource.name}</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">{datasource.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleAgentPanel}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              showAgentPanel
                ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
            title={showAgentPanel ? 'Hide agent activity' : 'Show agent activity'}
          >
            Agent
          </button>

          {hasMessages && (
            <button
              onClick={onNewConversation}
              disabled={isStreaming}
              className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Start a new conversation"
            >
              New Chat
            </button>
          )}
          {sessionId && (
            <div className="flex items-center text-xs text-green-600 dark:text-green-400">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
              Connected
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

import type { DataSource } from '../types'
import { useWittyMessages } from '../hooks/useWittyMessages'

interface MessageInputProps {
  input: string
  setInput: (value: string) => void
  isStreaming: boolean
  datasource: DataSource
  onSubmit: (e: React.FormEvent) => void
}

export default function MessageInput({
  input,
  setInput,
  isStreaming,
  datasource,
  onSubmit,
}: MessageInputProps) {
  const processingMessage = useWittyMessages(isStreaming, 'thinking', 2500)

  return (
    <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-800 p-4 bg-white dark:bg-gray-900 transition-colors duration-200">
      <form onSubmit={onSubmit} className="max-w-4xl mx-auto">
        <div className="flex items-end space-x-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask me anything about ${datasource.name}...`}
            className="flex-1 bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white rounded-3xl px-5 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all placeholder-gray-500 dark:placeholder-gray-400 border border-transparent hover:border-gray-300 dark:hover:border-gray-700"
            disabled={isStreaming}
            autoFocus
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white p-3 rounded-full transition-all shadow-sm hover:shadow-md disabled:shadow-none"
            aria-label="Send message"
          >
            {isStreaming ? (
              <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
          {isStreaming ? (
            <span className="text-blue-600 dark:text-blue-400 transition-all duration-300">
              {processingMessage}
            </span>
          ) : (
            'Press Enter to send'
          )}
        </p>
      </form>
    </div>
  )
}

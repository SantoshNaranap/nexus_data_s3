import { useState, useRef, useEffect } from 'react'
import { chatApi } from '../services/api'
import type { DataSource, ChatMessage } from '../types'
import MarkdownMessage from './MarkdownMessage'

interface ChatInterfaceProps {
  datasource: DataSource
}

const dataSourceIcons: Record<string, string> = {
  s3: '🪣',
  mysql: '🐬',
  jira: '📋',
  shopify: '🛍️',
  google_workspace: '📝',
}

export default function ChatInterface({ datasource }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingMessage, setStreamingMessage] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingMessage])

  // Reset session when datasource changes
  useEffect(() => {
    setMessages([])
    setSessionId(null)
    setStreamingMessage('')
  }, [datasource.id])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!input.trim() || isStreaming) return

    const userMessage: ChatMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])
    const messageText = input
    setInput('')
    setIsStreaming(true)
    setStreamingMessage('')

    let accumulatedMessage = ''

    try {
      await chatApi.sendMessageStream(
        {
          message: messageText,
          datasource: datasource.id,
          session_id: sessionId || undefined,
        },
        // onChunk
        (chunk) => {
          accumulatedMessage += chunk
          setStreamingMessage(accumulatedMessage)
        },
        // onSession
        (newSessionId) => {
          setSessionId(newSessionId)
        },
        // onDone
        () => {
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: accumulatedMessage,
              timestamp: new Date().toISOString(),
            },
          ])
          setStreamingMessage('')
          setIsStreaming(false)
        },
        // onError
        (error) => {
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: `Error: ${error}. Please try again.`,
              timestamp: new Date().toISOString(),
            },
          ])
          setStreamingMessage('')
          setIsStreaming(false)
        }
      )
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`,
          timestamp: new Date().toISOString(),
        },
      ])
      setStreamingMessage('')
      setIsStreaming(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
      {/* Data source header - Google style */}
      <div className="flex-shrink-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4 transition-colors duration-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="text-2xl">
              {dataSourceIcons[datasource.id] || '📊'}
            </div>
            <div>
              <h2 className="font-medium text-gray-900 dark:text-white">{datasource.name}</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">{datasource.description}</p>
            </div>
          </div>
          {sessionId && (
            <div className="flex items-center text-xs text-green-600 dark:text-green-400">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
              Connected
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 && !isStreaming && (
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
              <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-3">💡 Try asking:</p>
              <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                {datasource.id === 'mysql' && (
                  <>
                    <p>"Show me the latest users"</p>
                    <p>"How many rows are in the orders table?"</p>
                  </>
                )}
                {datasource.id === 's3' && (
                  <>
                    <p>"What buckets do I have?"</p>
                    <p>"Show me files in my bucket"</p>
                  </>
                )}
                {datasource.id === 'google_workspace' && (
                  <>
                    <p>"Show me my recent Google Docs"</p>
                    <p>"List my spreadsheets"</p>
                    <p>"What's on my calendar today?"</p>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${
              message.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-3xl rounded-2xl px-5 py-4 ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : message.content.startsWith('Error:')
                  ? 'bg-red-50 dark:bg-red-900/20 text-red-900 dark:text-red-200 border border-red-200 dark:border-red-800'
                  : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700'
              } transition-colors duration-200`}
            >
              {message.role === 'user' ? (
                <div className="whitespace-pre-wrap break-words leading-relaxed text-sm">
                  {message.content}
                </div>
              ) : (
                <MarkdownMessage content={message.content} />
              )}
              {message.timestamp && (
                <div className="text-xs opacity-60 mt-3">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </div>
              )}
            </div>
          </div>
        ))}

        {streamingMessage && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-2xl px-5 py-4 max-w-3xl border border-gray-200 dark:border-gray-700 transition-colors duration-200">
              <div className="relative">
                <MarkdownMessage content={streamingMessage} />
                <span className="inline-block w-0.5 h-4 bg-blue-600 dark:bg-blue-400 ml-1 animate-pulse align-middle"></span>
              </div>
            </div>
          </div>
        )}

        {isStreaming && !streamingMessage && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 rounded-2xl px-5 py-3 border border-gray-200 dark:border-gray-700 transition-colors duration-200">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-gray-400 dark:bg-gray-600 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                <div className="w-2 h-2 bg-gray-400 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input - Google style */}
      <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-800 p-4 bg-white dark:bg-gray-900 transition-colors duration-200">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
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
              <span className="text-blue-600 dark:text-blue-400">Processing your request...</span>
            ) : (
              'Press Enter to send'
            )}
          </p>
        </form>
      </div>
    </div>
  )
}

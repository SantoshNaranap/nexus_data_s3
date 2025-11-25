import { useState, useRef, useEffect } from 'react'
import { chatApi } from '../services/api'
import type { DataSource, ChatMessage } from '../types'

interface ChatInterfaceProps {
  datasource: DataSource
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
    <div className="flex-1 flex flex-col">
      {/* Data source header */}
      <div className="bg-gray-800 border-b border-gray-700 px-6 py-3">
        <div className="flex items-center">
          <span className="text-2xl mr-3">
            {datasource.id === 's3' && '🪣'}
            {datasource.id === 'mysql' && '🐬'}
            {datasource.id === 'jira' && '📋'}
            {datasource.id === 'shopify' && '🛍️'}
          </span>
          <div>
            <h2 className="font-semibold">{datasource.name}</h2>
            <p className="text-xs text-gray-400">{datasource.description}</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-8">
            <p>Start a conversation with {datasource.name}</p>
            <p className="text-sm mt-2">
              Ask questions in natural language about your data
            </p>
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
              className={`max-w-3xl rounded-lg px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-100'
              }`}
            >
              <div className="whitespace-pre-wrap break-words">
                {message.content}
              </div>
              {message.timestamp && (
                <div className="text-xs opacity-70 mt-1">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </div>
              )}
            </div>
          </div>
        ))}

        {streamingMessage && (
          <div className="flex justify-start">
            <div className="bg-gray-700 text-gray-100 rounded-lg px-4 py-3 max-w-3xl">
              <div className="whitespace-pre-wrap break-words">
                {streamingMessage}
                <span className="inline-block w-2 h-4 bg-blue-500 ml-1 animate-pulse"></span>
              </div>
            </div>
          </div>
        )}

        {isStreaming && !streamingMessage && (
          <div className="flex justify-start">
            <div className="bg-gray-700 rounded-lg px-4 py-3">
              <div className="flex space-x-2">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-700 p-4">
        <form onSubmit={handleSubmit} className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask a question about ${datasource.name}...`}
            className="flex-1 bg-gray-800 text-white rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-medium transition-colors"
          >
            Send
          </button>
        </form>
        <p className="text-xs text-gray-500 mt-2">
          Press Enter to send • Using Claude AI with MCP
        </p>
      </div>
    </div>
  )
}

import { useRef, useEffect, useState } from 'react'
import type { ChatMessage } from '../types'
import MarkdownMessage from './MarkdownMessage'
import ThinkingIndicator, { ThinkingIndicatorStreaming } from './ThinkingIndicator'
import { useWittyMessages } from '../hooks/useWittyMessages'

interface MessageListProps {
  messages: ChatMessage[]
  streamingMessage: string
  thinkingContent: string
  isActivelyThinking: boolean
  isStreaming: boolean
  onFollowUpClick: (question: string) => void
}

export default function MessageList({
  messages,
  streamingMessage,
  thinkingContent,
  isActivelyThinking,
  isStreaming,
  onFollowUpClick,
}: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null)

  const connectingMessage = useWittyMessages(isStreaming && !thinkingContent && !streamingMessage, 'connecting', 2000)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingMessage])

  const handleCopyMessage = async (content: string, index: number) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMessageIndex(index)
      setTimeout(() => setCopiedMessageIndex(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {messages.map((message, index) => (
        <div
          key={index}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
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
              <>
                {message.thinkingContent && (
                  <ThinkingIndicator content={message.thinkingContent} />
                )}
                <MarkdownMessage content={message.content} />

                {message.sources && message.sources.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700">
                    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                      </svg>
                      <span className="font-medium">Sources</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {message.sources.map((source, idx) => (
                        <div
                          key={idx}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-100 dark:bg-gray-700 rounded-full text-xs text-gray-700 dark:text-gray-300"
                        >
                          <span className="w-4 h-4 flex items-center justify-center bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 rounded-full text-[10px] font-bold">
                            {idx + 1}
                          </span>
                          <span>{source.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {message.followUpQuestions && message.followUpQuestions.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700">
                    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="font-medium">Related</span>
                    </div>
                    <div className="space-y-1.5">
                      {message.followUpQuestions.map((question, idx) => (
                        <button
                          key={idx}
                          onClick={() => onFollowUpClick(question)}
                          disabled={isStreaming}
                          className="w-full text-left px-3 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                          <span>{question}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
            {message.timestamp && (
              <div className="text-xs opacity-60 mt-3 flex items-center gap-2">
                <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
                {message.responseTime && (
                  <>
                    <span>-</span>
                    <span className="text-green-600 dark:text-green-400">
                      {message.responseTime < 1000
                        ? `${Math.round(message.responseTime)}ms`
                        : `${(message.responseTime / 1000).toFixed(1)}s`}
                    </span>
                  </>
                )}
                {message.role === 'assistant' && !message.content.startsWith('Error:') && (
                  <>
                    <span>-</span>
                    <button
                      onClick={() => handleCopyMessage(message.content, index)}
                      className="flex items-center gap-1 hover:opacity-100 opacity-70 transition-opacity"
                      title="Copy to clipboard"
                    >
                      {copiedMessageIndex === index ? (
                        <>
                          <svg className="w-3.5 h-3.5 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          <span className="text-green-600 dark:text-green-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      ))}

      {isStreaming && (
        <div className="flex justify-start">
          <div className="max-w-3xl w-full">
            {(thinkingContent || isActivelyThinking) && !streamingMessage && (
              <ThinkingIndicatorStreaming content={thinkingContent} isActive={isActivelyThinking} />
            )}
            {streamingMessage && (
              <div className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-2xl px-5 py-4 border border-gray-200 dark:border-gray-700 transition-colors duration-200">
                {thinkingContent && <ThinkingIndicator content={thinkingContent} />}
                <div className="relative">
                  <MarkdownMessage content={streamingMessage} />
                  <span className="inline-block w-0.5 h-4 bg-blue-600 dark:bg-blue-400 ml-1 animate-pulse align-middle"></span>
                </div>
              </div>
            )}
            {!thinkingContent && !isActivelyThinking && !streamingMessage && (
              <div className="bg-white dark:bg-gray-800 rounded-2xl px-5 py-3 border border-gray-200 dark:border-gray-700 transition-colors duration-200">
                <div className="flex items-center space-x-3">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                  <span className="text-sm text-gray-500 dark:text-gray-400 transition-all duration-300">
                    {connectingMessage}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  )
}

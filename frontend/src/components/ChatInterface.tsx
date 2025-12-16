import { useState, useRef, useEffect } from 'react'
import { chatApi } from '../services/api'
import { agentApi } from '../services/agentApi'
import type { DataSource, ChatMessage, AgentStep, SourceReference } from '../types'
import MarkdownMessage from './MarkdownMessage'
import AgentActivityPanel from './AgentActivityPanel'
import { SessionManager } from '../utils/sessionManager'
import DataSourceIcon from './DataSourceIcon'
import ThinkingIndicator, { ThinkingIndicatorStreaming } from './ThinkingIndicator'
import { useWittyMessages } from '../hooks/useWittyMessages'

interface ChatInterfaceProps {
  datasource: DataSource
}

export default function ChatInterface({ datasource }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [_statusMessage, setStatusMessage] = useState('')
  const [_isThinking, setIsThinking] = useState(false)
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([])
  const [showAgentPanel, setShowAgentPanel] = useState(true)
  const [currentThought, setCurrentThought] = useState<string | undefined>()
  const [_currentSources, setCurrentSources] = useState<SourceReference[]>([])
  const [_followUpQuestions, setFollowUpQuestions] = useState<string[]>([])
  const [thinkingContent, setThinkingContent] = useState<string>('')
  const [_thinkingExpanded, setThinkingExpanded] = useState(true)
  const [isActivelyThinking, setIsActivelyThinking] = useState(false)
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Witty rotating messages during loading
  const connectingMessage = useWittyMessages(isStreaming && !thinkingContent && !streamingMessage, 'connecting', 2000)
  const processingMessage = useWittyMessages(isStreaming, 'thinking', 2500)

  // Step counter for unique IDs
  const stepCounter = useRef(0)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const handleNewConversation = () => {
    if (confirm('Start a new conversation? This will clear your chat history for this datasource.')) {
      const newSessionId = SessionManager.startNewSession(datasource.id)
      setSessionId(newSessionId)
      setMessages([])
      setStreamingMessage('')
      setAgentSteps([])
      console.log(`[ChatInterface] Started new conversation for ${datasource.id}:`, newSessionId)
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingMessage])

  // Load or create session from localStorage when datasource changes
  useEffect(() => {
    setMessages([])
    setStreamingMessage('')
    setAgentSteps([])
    // Load existing session from localStorage or create new one
    const persistedSessionId = SessionManager.getSessionId(datasource.id)
    setSessionId(persistedSessionId)
    console.log(`[ChatInterface] Loaded session for ${datasource.id}:`, persistedSessionId)
  }, [datasource.id])

  // Helper to add or update an agent step
  const addAgentStep = (step: Partial<AgentStep> & { type: AgentStep['type']; title: string }) => {
    const newStep: AgentStep = {
      id: `step-${++stepCounter.current}`,
      status: 'active',
      timestamp: Date.now(),
      ...step,
    }
    setAgentSteps(prev => [...prev, newStep])
    return newStep.id
  }

  const updateAgentStep = (id: string, updates: Partial<AgentStep>) => {
    setAgentSteps(prev =>
      prev.map(step =>
        step.id === id ? { ...step, ...updates } : step
      )
    )
  }

  const completeAgentStep = (id: string, duration?: number) => {
    updateAgentStep(id, { status: 'complete', duration })
  }

  // Handle follow-up question click
  const handleFollowUpClick = (question: string) => {
    setInput(question)
  }

  // Copy message to clipboard
  const handleCopyMessage = async (content: string, index: number) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMessageIndex(index)
      setTimeout(() => setCopiedMessageIndex(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

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
    setStatusMessage('')
    setIsThinking(true)
    setAgentSteps([])
    setCurrentSources([])
    setFollowUpQuestions([])
    setThinkingContent('')
    setThinkingExpanded(true)
    setIsActivelyThinking(false)
    stepCounter.current = 0

    // Track start time for response timing
    const startTime = performance.now()
    let accumulatedMessage = ''
    let hasRealContent = false
    let accumulatedThinking = '' // Track thinking content for saving with message

    // Add initial thinking step
    const thinkingStepId = addAgentStep({
      type: 'thinking',
      title: datasource.id === 'all_sources' ? 'Planning multi-source query' : 'Analyzing query',
      description: datasource.id === 'all_sources' ? 'Detecting relevant sources...' : 'Understanding your request...',
    })

    try {
      // Check if this is a multi-source query
      if (datasource.id === 'all_sources') {
        // Use agent API for multi-source queries
        await agentApi.queryStream(
          {
            query: messageText,
            session_id: sessionId || undefined,
            include_plan: true,
          },
          {
            onStarted: (newSessionId) => {
              setSessionId(newSessionId)
            },
            onPlanning: () => {
              setCurrentThought('Analyzing which sources to query...')
              accumulatedThinking = 'Planning multi-source query...'
              setThinkingContent(accumulatedThinking)
            },
            onPlanComplete: (sources, reasoning) => {
              completeAgentStep(thinkingStepId, performance.now() - startTime)
              accumulatedThinking += `\nWill query: ${sources.join(', ')}\n${reasoning}`
              setThinkingContent(accumulatedThinking)

              // Add a step for the plan
              addAgentStep({
                type: 'planning',
                title: `Querying ${sources.length} sources`,
                description: sources.join(', '),
              })
            },
            onSourceStart: (source) => {
              setCurrentThought(`Querying ${source}...`)
              addAgentStep({
                type: 'tool_call',
                title: `Querying ${source}`,
                description: `Fetching data from ${source}`,
                details: { datasource: source },
              })
            },
            onSourceComplete: (source, success, error) => {
              // Update the step for this source
              setAgentSteps(prev => {
                const sourceStep = prev.find(s => s.details?.datasource === source && s.status === 'active')
                if (sourceStep) {
                  return prev.map(s =>
                    s.id === sourceStep.id
                      ? { ...s, status: success ? 'complete' as const : 'error' as const, description: error || `Got results from ${source}` }
                      : s
                  )
                }
                return prev
              })
              accumulatedThinking += `\n${success ? '✓' : '✗'} ${source}: ${error || 'success'}`
              setThinkingContent(accumulatedThinking)
            },
            onSynthesizing: () => {
              setCurrentThought('Synthesizing results...')
              setIsThinking(false)
              hasRealContent = true
              addAgentStep({
                type: 'synthesizing',
                title: 'Synthesizing response',
                description: 'Combining results from all sources...',
              })
            },
            onSynthesisChunk: (chunk) => {
              accumulatedMessage += chunk
              setStreamingMessage(accumulatedMessage)
            },
            onDone: (result) => {
              const endTime = performance.now()
              const responseTime = endTime - startTime

              // Create sources from successful sources
              const sources: SourceReference[] = result.successful_sources.map(s => ({
                type: 'datasource' as const,
                name: s,
              }))

              // Complete all steps
              setAgentSteps(prev => {
                const updated = prev.map(s =>
                  s.status === 'active'
                    ? { ...s, status: 'complete' as const, duration: responseTime }
                    : s
                )
                return [...updated, {
                  id: `step-${++stepCounter.current}`,
                  type: 'complete' as const,
                  title: 'Response ready',
                  description: `Queried ${result.successful_sources.length} sources in ${(responseTime / 1000).toFixed(1)}s`,
                  status: 'complete' as const,
                  timestamp: Date.now(),
                  duration: responseTime,
                }]
              })

              setMessages((prev) => [
                ...prev,
                {
                  role: 'assistant',
                  content: accumulatedMessage,
                  timestamp: new Date().toISOString(),
                  responseTime,
                  sources,
                  thinkingContent: accumulatedThinking || undefined,
                },
              ])
              setStreamingMessage('')
              setStatusMessage('')
              setIsThinking(false)
              setIsStreaming(false)
              setCurrentThought(undefined)
            },
            onError: (error) => {
              setAgentSteps(prev => prev.map(s =>
                s.status === 'active'
                  ? { ...s, status: 'error' as const, description: error }
                  : s
              ))

              setMessages((prev) => [
                ...prev,
                {
                  role: 'assistant',
                  content: `Error: ${error}. Please try again.`,
                  timestamp: new Date().toISOString(),
                },
              ])
              setStreamingMessage('')
              setStatusMessage('')
              setIsThinking(false)
              setIsStreaming(false)
              setCurrentThought(undefined)
            },
          }
        )
      } else {
        // Single-source query - use regular chat API
        await chatApi.sendMessageStream(
          {
            message: messageText,
            datasource: datasource.id,
            session_id: sessionId || undefined,
          },
          // onChunk
          (chunk) => {
            accumulatedMessage += chunk

            // Detect status updates from the chunk
            const isStatusUpdate = /^[🎫🪣🗄️📊✓⚡📋🔄🧠]\s*\*?.+\*?\.{3}/.test(chunk) ||
                                   chunk.includes('✓ Found') ||
                                   chunk.includes('Querying') ||
                                   chunk.includes('Searching') ||
                                   chunk.includes('Fetching') ||
                                   chunk.includes('Analyzing') ||
                                   chunk.includes('Loading')

            if (isStatusUpdate && !hasRealContent) {
              // Update agent panel with detected activity
              const statusText = chunk.replace(/[*_]/g, '').trim()
              setCurrentThought(statusText)
              setStatusMessage(accumulatedMessage)
              // Append to thinking content for the collapsible panel
              accumulatedThinking = accumulatedThinking ? `${accumulatedThinking}\n${statusText}` : statusText
              setThinkingContent(accumulatedThinking)

              // Complete thinking step and add appropriate step
              if (thinkingStepId && agentSteps.find(s => s.id === thinkingStepId)?.status === 'active') {
                completeAgentStep(thinkingStepId, performance.now() - startTime)
              }

              // Detect tool calls from status messages
              if (chunk.includes('Querying') || chunk.includes('query')) {
                addAgentStep({
                  type: 'tool_call',
                  title: `Querying ${datasource.name}`,
                  description: statusText,
                  details: { datasource: datasource.id },
                })
              } else if (chunk.includes('Found') || chunk.includes('found')) {
                addAgentStep({
                  type: 'analyzing',
                  title: 'Processing results',
                  description: statusText,
                })
              }
            } else {
              // Real content is starting
              if (!hasRealContent) {
                hasRealContent = true
                setIsThinking(false)
                setStatusMessage('')
                setCurrentThought(undefined)

                // Complete any active steps
                setAgentSteps(prev => prev.map(s =>
                  s.status === 'active'
                    ? { ...s, status: 'complete' as const, duration: performance.now() - startTime }
                    : s
                ))

                // Add synthesizing step
                addAgentStep({
                  type: 'synthesizing',
                  title: 'Generating response',
                  description: 'Composing the answer...',
                })
              }
              setStreamingMessage(accumulatedMessage)
            }
          },
          // onSession
          (newSessionId) => {
            setSessionId(newSessionId)
          },
          // onDone
          (metadata) => {
            // Calculate response time
            const endTime = performance.now()
            const responseTime = endTime - startTime

            // Store sources and follow-up questions from metadata
            const sources = metadata?.sources || []
            const followUps = metadata?.followUpQuestions || []
            setCurrentSources(sources)
            setFollowUpQuestions(followUps)

            // Complete all steps
            setAgentSteps(prev => {
              const updated = prev.map(s =>
                s.status === 'active'
                  ? { ...s, status: 'complete' as const, duration: responseTime }
                  : s
              )
              // Add completion step
              return [...updated, {
                id: `step-${++stepCounter.current}`,
                type: 'complete' as const,
                title: 'Response ready',
                description: `Completed in ${responseTime < 1000 ? `${Math.round(responseTime)}ms` : `${(responseTime / 1000).toFixed(1)}s`}`,
                status: 'complete' as const,
                timestamp: Date.now(),
                duration: responseTime,
              }]
            })

            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content: accumulatedMessage,
                timestamp: new Date().toISOString(),
                responseTime,
                sources,
                followUpQuestions: followUps,
                thinkingContent: accumulatedThinking || undefined,
              },
            ])
            setStreamingMessage('')
            setStatusMessage('')
            setIsThinking(false)
            setIsStreaming(false)
            setCurrentThought(undefined)
          },
          // onError
          (error) => {
            // Mark current step as error
            setAgentSteps(prev => prev.map(s =>
              s.status === 'active'
                ? { ...s, status: 'error' as const, description: error }
                : s
            ))

            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content: `Error: ${error}. Please try again.`,
                timestamp: new Date().toISOString(),
              },
            ])
            setStreamingMessage('')
            setStatusMessage('')
            setIsThinking(false)
            setIsStreaming(false)
            setCurrentThought(undefined)
          },
          // onAgentStep (from backend)
          (step) => {
            // Handle backend-provided agent steps
            setAgentSteps(prev => {
              const existingIndex = prev.findIndex(s => s.id === step.id)
              if (existingIndex >= 0) {
                // Update existing step
                const updated = [...prev]
                updated[existingIndex] = { ...updated[existingIndex], ...step }
                return updated
              }
              // Add new step
              return [...prev, step]
            })
          },
          // onSource (not used currently)
          undefined,
          // onThinking - handle streaming thinking content from Claude
          (thinkingText) => {
            accumulatedThinking += thinkingText
            setThinkingContent(accumulatedThinking)
          },
          // onThinkingStart - Claude started thinking
          () => {
            setIsActivelyThinking(true)
            setThinkingContent('')
            accumulatedThinking = ''
          },
          // onThinkingEnd - Claude finished thinking
          () => {
            setIsActivelyThinking(false)
          }
        )
      }
    } catch (error) {
      setAgentSteps(prev => [...prev, {
        id: `step-${++stepCounter.current}`,
        type: 'error',
        title: 'Request failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        timestamp: Date.now(),
      }])

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`,
          timestamp: new Date().toISOString(),
        },
      ])
      setStreamingMessage('')
      setStatusMessage('')
      setIsThinking(false)
      setIsStreaming(false)
      setCurrentThought(undefined)
    }
  }

  return (
    <div className="flex-1 flex h-full overflow-hidden bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Data source header - Google style */}
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
              {/* Agent Panel Toggle */}
              <button
                onClick={() => setShowAgentPanel(!showAgentPanel)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  showAgentPanel
                    ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
                title={showAgentPanel ? 'Hide agent activity' : 'Show agent activity'}
              >
                🧠 Agent
              </button>

              {messages.length > 0 && (
                <button
                  onClick={handleNewConversation}
                  disabled={isStreaming}
                  className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Start a new conversation"
                >
                  ✨ New Chat
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
                <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-3">Try asking:</p>
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
                  {datasource.id === 'jira' && (
                    <>
                      <p>"Show me my open issues"</p>
                      <p>"What's in the backlog?"</p>
                    </>
                  )}
                  {datasource.id === 'github' && (
                    <>
                      <p>"Show me my repositories"</p>
                      <p>"List open pull requests"</p>
                    </>
                  )}
                  {datasource.id === 'slack' && (
                    <>
                      <p>"What channels do I have?"</p>
                      <p>"Show team members"</p>
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
                  <>
                    {/* Thinking indicator - collapsible, shown above response */}
                    {message.thinkingContent && (
                      <ThinkingIndicator content={message.thinkingContent} />
                    )}
                    <MarkdownMessage content={message.content} />

                    {/* Sources - Perplexity style */}
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

                    {/* Follow-up questions - Perplexity style */}
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
                              onClick={() => handleFollowUpClick(question)}
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
                        <span>•</span>
                        <span className="text-green-600 dark:text-green-400">
                          {message.responseTime < 1000
                            ? `${Math.round(message.responseTime)}ms`
                            : `${(message.responseTime / 1000).toFixed(1)}s`}
                        </span>
                      </>
                    )}
                    {message.sources && message.sources.length > 0 && (
                      <>
                        <span>•</span>
                        <span className="text-blue-600 dark:text-blue-400">
                          {message.sources.length} source{message.sources.length > 1 ? 's' : ''}
                        </span>
                      </>
                    )}
                    {/* Copy button for assistant messages */}
                    {message.role === 'assistant' && !message.content.startsWith('Error:') && (
                      <>
                        <span>•</span>
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

          {/* Show thinking state - visible during streaming phase */}
          {isStreaming && (
            <div className="flex justify-start">
              <div className="max-w-3xl w-full">
                {/* Show thinking indicator when we have thinking content OR when actively thinking */}
                {(thinkingContent || isActivelyThinking) && !streamingMessage && (
                  <ThinkingIndicatorStreaming
                    content={thinkingContent}
                    isActive={isActivelyThinking}
                  />
                )}
                {/* Show streaming message if we have one */}
                {streamingMessage && (
                  <div className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-2xl px-5 py-4 border border-gray-200 dark:border-gray-700 transition-colors duration-200">
                    {/* Show collapsed thinking above the response */}
                    {thinkingContent && (
                      <ThinkingIndicator content={thinkingContent} />
                    )}
                    <div className="relative">
                      <MarkdownMessage content={streamingMessage} />
                      <span className="inline-block w-0.5 h-4 bg-blue-600 dark:bg-blue-400 ml-1 animate-pulse align-middle"></span>
                    </div>
                  </div>
                )}
                {/* Initial loading state before any content */}
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
                <span className="text-blue-600 dark:text-blue-400 transition-all duration-300">
                  {processingMessage}
                </span>
              ) : (
                'Press Enter to send'
              )}
            </p>
          </form>
        </div>
      </div>

      {/* Agent Activity Panel */}
      {showAgentPanel && (
        <AgentActivityPanel
          steps={agentSteps}
          isActive={isStreaming}
          currentThought={currentThought}
          onClose={() => setShowAgentPanel(false)}
        />
      )}
    </div>
  )
}

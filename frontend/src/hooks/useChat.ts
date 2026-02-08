import { useState, useRef, useEffect, useCallback } from 'react'
import { chatApi, diagnosticsApi } from '../services/api'
import { agentApi } from '../services/agentApi'
import type { DataSource, ChatMessage, AgentStep, SourceReference, ErrorInvestigation, RemediationResponse } from '../types'
import { SessionManager } from '../utils/sessionManager'
import { useErrorDetection } from './useErrorDetection'

interface UseChatProps {
  datasource: DataSource
}

interface UseChatReturn {
  messages: ChatMessage[]
  input: string
  setInput: (value: string) => void
  sessionId: string | null
  isStreaming: boolean
  streamingMessage: string
  agentSteps: AgentStep[]
  thinkingContent: string
  isActivelyThinking: boolean
  isInvestigating: boolean
  handleSubmit: (e: React.FormEvent) => Promise<void>
  handleNewConversation: () => void
  handleFollowUpClick: (question: string) => void
}

export function useChat({ datasource }: UseChatProps): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([])
  const [thinkingContent, setThinkingContent] = useState<string>('')
  const [isActivelyThinking, setIsActivelyThinking] = useState(false)
  const [_currentSources, setCurrentSources] = useState<SourceReference[]>([])
  const [_followUpQuestions, setFollowUpQuestions] = useState<string[]>([])
  const [isInvestigating, setIsInvestigating] = useState(false)

  const abortControllerRef = useRef<AbortController | null>(null)
  const stepCounter = useRef(0)
  const { detectError } = useErrorDetection()
  const pendingUserQuery = useRef<string>('')

  // Reset state when datasource changes
  useEffect(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    setMessages([])
    setStreamingMessage('')
    setAgentSteps([])
    setIsStreaming(false)
    setThinkingContent('')
    setIsActivelyThinking(false)

    const persistedSessionId = SessionManager.getSessionId(datasource.id)
    setSessionId(persistedSessionId)

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [datasource.id])

  const addAgentStep = useCallback((step: Partial<AgentStep> & { type: AgentStep['type']; title: string }) => {
    const newStep: AgentStep = {
      id: `step-${++stepCounter.current}`,
      status: 'active',
      timestamp: Date.now(),
      ...step,
    }
    setAgentSteps(prev => [...prev, newStep])
    return newStep.id
  }, [])

  const completeAgentStep = useCallback((id: string, duration?: number) => {
    setAgentSteps(prev =>
      prev.map(step =>
        step.id === id ? { ...step, status: 'complete' as const, duration } : step
      )
    )
  }, [])

  // Investigate error, attempt auto-fix, and attach results to the last message
  const investigateError = useCallback(async (content: string, userQuery: string) => {
    console.log('[ErrorAgent] Checking response for errors...')
    if (!detectError(content)) {
      console.log('[ErrorAgent] No error detected, skipping')
      return
    }

    console.log('[ErrorAgent] Error detected! Starting investigation and auto-fix for', datasource.id)
    setIsInvestigating(true)
    try {
      // Step 1: Investigate to understand the problem
      const investigation = await diagnosticsApi.investigate({
        error_message: content,
        datasource: datasource.id,
        user_query: userQuery,
        session_id: sessionId || undefined,
      })

      // Attach investigation to the last message immediately (shows findings)
      setMessages(prev => {
        const updated = [...prev]
        const lastIndex = updated.length - 1
        if (lastIndex >= 0 && updated[lastIndex].role === 'assistant') {
          updated[lastIndex] = {
            ...updated[lastIndex],
            errorInvestigation: { ...investigation, status: 'investigating' as const },
          }
        }
        return updated
      })

      // Step 2: Attempt auto-remediation
      let remediation: RemediationResponse | null = null
      try {
        remediation = await diagnosticsApi.remediate(datasource.id, sessionId || undefined)
      } catch (remErr) {
        console.error('Auto-remediation failed:', remErr)
      }

      // Step 3: Update the message with final investigation + remediation results
      setMessages(prev => {
        const updated = [...prev]
        const lastIndex = updated.length - 1
        if (lastIndex >= 0 && updated[lastIndex].role === 'assistant') {
          const finalInvestigation: ErrorInvestigation = {
            ...investigation,
            status: 'completed',
          }

          // If remediation succeeded, add a finding about it
          if (remediation) {
            const remediationFinding = {
              category: 'connection' as const,
              severity: remediation.connection_restored ? 'info' as const : 'warning' as const,
              title: remediation.connection_restored
                ? 'Auto-fix successful'
                : remediation.status === 'partial'
                  ? 'Partial fix applied'
                  : 'Auto-fix failed',
              detail: remediation.message,
              suggested_action: remediation.connection_restored
                ? 'Please retry your query'
                : 'Go to Settings and reconnect this datasource',
            }
            finalInvestigation.findings = [...investigation.findings, remediationFinding]

            // Update recommendations
            if (remediation.connection_restored) {
              finalInvestigation.recommendations = ['Your query should work now — please retry.']
            } else {
              finalInvestigation.recommendations = [
                ...investigation.recommendations,
                `Auto-fix status: ${remediation.status}. ${remediation.message}`,
              ]
            }
          }

          updated[lastIndex] = {
            ...updated[lastIndex],
            errorInvestigation: finalInvestigation,
          }
        }
        return updated
      })
    } catch (error) {
      console.error('Error investigation failed:', error)
    } finally {
      setIsInvestigating(false)
    }
  }, [detectError, datasource.id, sessionId])

  const handleNewConversation = useCallback(() => {
    if (confirm('Start a new conversation? This will clear your chat history for this datasource.')) {
      const newSessionId = SessionManager.startNewSession(datasource.id)
      setSessionId(newSessionId)
      setMessages([])
      setStreamingMessage('')
      setAgentSteps([])
    }
  }, [datasource.id])

  const handleFollowUpClick = useCallback((question: string) => {
    setInput(question)
  }, [])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()

    if (!input.trim() || isStreaming) return

    abortControllerRef.current = new AbortController()
    const abortSignal = abortControllerRef.current.signal

    const userMessage: ChatMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    }

    setMessages(prev => [...prev, userMessage])
    const messageText = input
    pendingUserQuery.current = messageText  // Store for error investigation
    setInput('')
    setIsStreaming(true)
    setStreamingMessage('')
    setAgentSteps([])
    setCurrentSources([])
    setFollowUpQuestions([])
    setThinkingContent('')
    setIsActivelyThinking(false)
    stepCounter.current = 0

    const startTime = performance.now()
    let accumulatedMessage = ''
    let hasRealContent = false
    let accumulatedThinking = ''

    const thinkingStepId = addAgentStep({
      type: 'thinking',
      title: datasource.id === 'all_sources' ? 'Planning multi-source query' : 'Analyzing query',
      description: datasource.id === 'all_sources' ? 'Detecting relevant sources...' : 'Understanding your request...',
    })

    try {
      if (datasource.id === 'all_sources') {
        await agentApi.queryStream(
          {
            query: messageText,
            session_id: sessionId || undefined,
            include_plan: true,
          },
          {
            onStarted: (newSessionId) => setSessionId(newSessionId),
            onPlanning: () => {
              accumulatedThinking = 'Planning multi-source query...'
              setThinkingContent(accumulatedThinking)
            },
            onPlanComplete: (sources, reasoning) => {
              completeAgentStep(thinkingStepId, performance.now() - startTime)
              accumulatedThinking += `\nWill query: ${sources.join(', ')}\n${reasoning}`
              setThinkingContent(accumulatedThinking)
              addAgentStep({
                type: 'planning',
                title: `Querying ${sources.length} sources`,
                description: sources.join(', '),
              })
            },
            onSourceStart: (source) => {
              addAgentStep({
                type: 'tool_call',
                title: `Querying ${source}`,
                description: `Fetching data from ${source}`,
                details: { datasource: source },
              })
            },
            onSourceComplete: (source, success, error) => {
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
            },
            onSynthesizing: () => {
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
              const responseTime = performance.now() - startTime
              const sources: SourceReference[] = result.successful_sources.map(s => ({
                type: 'datasource' as const,
                name: s,
              }))

              setAgentSteps(prev => {
                const updated = prev.map(s =>
                  s.status === 'active' ? { ...s, status: 'complete' as const, duration: responseTime } : s
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

              setMessages(prev => [
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
              setIsStreaming(false)

              // Investigate errors in the response
              investigateError(accumulatedMessage, pendingUserQuery.current)
            },
            onError: (error) => {
              setAgentSteps(prev => prev.map(s =>
                s.status === 'active' ? { ...s, status: 'error' as const, description: error } : s
              ))
              const errorContent = `Error: ${error}. Please try again.`
              setMessages(prev => [
                ...prev,
                { role: 'assistant', content: errorContent, timestamp: new Date().toISOString() },
              ])
              setStreamingMessage('')
              setIsStreaming(false)

              // Investigate and auto-fix streaming errors
              investigateError(errorContent, pendingUserQuery.current)
            },
          },
          abortSignal
        )
      } else {
        await chatApi.sendMessageStream(
          {
            message: messageText,
            datasource: datasource.id,
            session_id: sessionId || undefined,
          },
          (chunk) => {
            accumulatedMessage += chunk
            if (!hasRealContent) {
              hasRealContent = true
              completeAgentStep(thinkingStepId, performance.now() - startTime)
            }
            setStreamingMessage(accumulatedMessage)
          },
          (newSessionId) => setSessionId(newSessionId),
          (metadata) => {
            const responseTime = performance.now() - startTime
            const sources = metadata?.sources || []
            const followUps = metadata?.followUpQuestions || []
            setCurrentSources(sources)
            setFollowUpQuestions(followUps)

            setAgentSteps(prev => {
              const updated = prev.map(s =>
                s.status === 'active' ? { ...s, status: 'complete' as const, duration: responseTime } : s
              )
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

            setMessages(prev => [
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
            setIsStreaming(false)

            // Investigate errors in the response
            investigateError(accumulatedMessage, pendingUserQuery.current)
          },
          (error) => {
            setAgentSteps(prev => prev.map(s =>
              s.status === 'active' ? { ...s, status: 'error' as const, description: error } : s
            ))
            const errorContent = `Error: ${error}. Please try again.`
            setMessages(prev => [
              ...prev,
              { role: 'assistant', content: errorContent, timestamp: new Date().toISOString() },
            ])
            setStreamingMessage('')
            setIsStreaming(false)

            // Investigate and auto-fix streaming errors
            investigateError(errorContent, pendingUserQuery.current)
          },
          undefined,
          undefined,
          (thinkingText) => {
            accumulatedThinking += thinkingText
            setThinkingContent(accumulatedThinking)
          },
          () => {
            setIsActivelyThinking(true)
            setThinkingContent('')
            accumulatedThinking = ''
          },
          () => setIsActivelyThinking(false),
          abortSignal
        )
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return
      }
      setAgentSteps(prev => [...prev, {
        id: `step-${++stepCounter.current}`,
        type: 'error',
        title: 'Request failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        timestamp: Date.now(),
      }])
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`, timestamp: new Date().toISOString() },
      ])
      setStreamingMessage('')
      setIsStreaming(false)
    }
  }, [input, isStreaming, sessionId, datasource.id, addAgentStep, completeAgentStep, investigateError])

  return {
    messages,
    input,
    setInput,
    sessionId,
    isStreaming,
    streamingMessage,
    agentSteps,
    thinkingContent,
    isActivelyThinking,
    isInvestigating,
    handleSubmit,
    handleNewConversation,
    handleFollowUpClick,
  }
}

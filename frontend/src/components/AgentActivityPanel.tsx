import { useState, useEffect, useRef } from 'react'

export interface AgentStep {
  id: string
  type: 'thinking' | 'planning' | 'tool_call' | 'analyzing' | 'synthesizing' | 'complete' | 'error'
  title: string
  description?: string
  status: 'pending' | 'active' | 'complete' | 'error'
  timestamp: number
  duration?: number
  details?: {
    tool?: string
    datasource?: string
    result?: string
  }
}

interface AgentActivityPanelProps {
  steps: AgentStep[]
  isActive: boolean
  currentThought?: string
  onClose?: () => void
}

const stepIcons: Record<AgentStep['type'], string> = {
  thinking: '🧠',
  planning: '📋',
  tool_call: '🔧',
  analyzing: '🔍',
  synthesizing: '✨',
  complete: '✅',
  error: '❌',
}

const stepColors: Record<AgentStep['type'], string> = {
  thinking: 'text-purple-500',
  planning: 'text-blue-500',
  tool_call: 'text-orange-500',
  analyzing: 'text-cyan-500',
  synthesizing: 'text-green-500',
  complete: 'text-green-600',
  error: 'text-red-500',
}

const statusBgColors: Record<AgentStep['status'], string> = {
  pending: 'bg-gray-100 dark:bg-gray-800',
  active: 'bg-blue-50 dark:bg-blue-900/30 border-l-4 border-blue-500',
  complete: 'bg-green-50 dark:bg-green-900/20',
  error: 'bg-red-50 dark:bg-red-900/20',
}

// Thinking animation messages
const thinkingMessages = [
  "Analyzing your query...",
  "Understanding the context...",
  "Identifying data sources...",
  "Planning approach...",
  "Formulating response...",
  "Processing information...",
  "Connecting the dots...",
  "Reasoning through data...",
]

export default function AgentActivityPanel({
  steps,
  isActive,
  currentThought,
  onClose,
}: AgentActivityPanelProps) {
  const [thinkingMessageIndex, setThinkingMessageIndex] = useState(0)
  const [showPulse, setShowPulse] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Rotate thinking messages
  useEffect(() => {
    if (!isActive) return

    const interval = setInterval(() => {
      setThinkingMessageIndex((prev) => (prev + 1) % thinkingMessages.length)
    }, 2500)

    return () => clearInterval(interval)
  }, [isActive])

  // Pulse animation toggle
  useEffect(() => {
    if (!isActive) return

    const interval = setInterval(() => {
      setShowPulse((prev) => !prev)
    }, 500)

    return () => clearInterval(interval)
  }, [isActive])

  // Auto scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [steps])

  const activeStep = steps.find(s => s.status === 'active')
  const hasActiveStep = !!activeStep

  return (
    <div className="w-80 bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-800 flex flex-col h-full transition-colors duration-200">
      {/* Header */}
      <div className="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`relative ${isActive ? 'animate-pulse' : ''}`}>
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center">
                <span className="text-white text-sm">AI</span>
              </div>
              {isActive && (
                <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-green-500 rounded-full border-2 border-white dark:border-gray-900" />
              )}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Agent Activity</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {isActive ? 'Working...' : steps.length > 0 ? 'Completed' : 'Idle'}
              </p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Brain Animation */}
      {isActive && (
        <div className="flex-shrink-0 p-4 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/20 dark:to-blue-900/20 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-3">
            {/* Animated Brain/Thinking Visual */}
            <div className="relative">
              <svg
                className="w-12 h-12 text-purple-500 dark:text-purple-400"
                viewBox="0 0 24 24"
                fill="none"
              >
                {/* Brain outline */}
                <path
                  className={`${showPulse ? 'opacity-100' : 'opacity-70'} transition-opacity duration-300`}
                  d="M12 3C7.5 3 4 6.5 4 11c0 2.5 1 4.5 2.5 6l.5 4h10l.5-4c1.5-1.5 2.5-3.5 2.5-6 0-4.5-3.5-8-8-8z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  fill="none"
                />
                {/* Neural connection lines */}
                <path
                  className="animate-pulse"
                  d="M8 9h2m4 0h2M9 12h6M10 15h4"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                {/* Thinking sparks */}
                <circle
                  className={`${showPulse ? 'opacity-100' : 'opacity-0'} transition-opacity duration-200`}
                  cx="7" cy="7" r="1"
                  fill="currentColor"
                />
                <circle
                  className={`${!showPulse ? 'opacity-100' : 'opacity-0'} transition-opacity duration-200`}
                  cx="17" cy="8" r="1"
                  fill="currentColor"
                />
              </svg>

              {/* Orbiting dots */}
              <div className="absolute inset-0 animate-spin" style={{ animationDuration: '3s' }}>
                <div className="absolute top-0 left-1/2 w-1.5 h-1.5 bg-blue-500 rounded-full -translate-x-1/2 -translate-y-1" />
              </div>
              <div className="absolute inset-0 animate-spin" style={{ animationDuration: '4s', animationDirection: 'reverse' }}>
                <div className="absolute bottom-0 left-1/2 w-1.5 h-1.5 bg-purple-500 rounded-full -translate-x-1/2 translate-y-1" />
              </div>
            </div>

            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900 dark:text-white animate-pulse">
                {currentThought || thinkingMessages[thinkingMessageIndex]}
              </p>
              {/* Progress bar */}
              <div className="mt-2 h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-purple-500 to-blue-500 rounded-full animate-pulse"
                  style={{
                    width: `${Math.min(100, (steps.filter(s => s.status === 'complete').length / Math.max(1, steps.length)) * 100)}%`,
                    transition: 'width 0.5s ease-out'
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Steps List */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2">
        {steps.length === 0 && !isActive && (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <p className="text-sm">Agent activity will appear here</p>
          </div>
        )}

        {steps.map((step, index) => (
          <div
            key={step.id}
            className={`rounded-lg p-3 transition-all duration-300 ${statusBgColors[step.status]} ${
              step.status === 'active' ? 'transform scale-[1.02] shadow-sm' : ''
            }`}
          >
            <div className="flex items-start gap-2">
              {/* Status indicator */}
              <div className={`flex-shrink-0 ${step.status === 'active' ? 'animate-bounce' : ''}`}>
                {step.status === 'active' ? (
                  <div className="w-5 h-5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                ) : (
                  <span className="text-lg">{stepIcons[step.type]}</span>
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <p className={`text-sm font-medium ${stepColors[step.type]} truncate`}>
                    {step.title}
                  </p>
                  {step.duration && (
                    <span className="text-xs text-gray-400 ml-2 flex-shrink-0">
                      {step.duration}ms
                    </span>
                  )}
                </div>

                {step.description && (
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                    {step.description}
                  </p>
                )}

                {step.details?.tool && (
                  <div className="mt-1.5 inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs text-gray-600 dark:text-gray-300">
                    <span className="font-mono">{step.details.tool}</span>
                    {step.details.datasource && (
                      <>
                        <span className="text-gray-400">@</span>
                        <span>{step.details.datasource}</span>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Connection line to next step */}
            {index < steps.length - 1 && (
              <div className="ml-2.5 mt-2 h-4 w-px bg-gray-300 dark:bg-gray-600" />
            )}
          </div>
        ))}

        {/* Active thinking indicator at bottom */}
        {isActive && !hasActiveStep && (
          <div className="rounded-lg p-3 bg-purple-50 dark:bg-purple-900/20 border-l-4 border-purple-500">
            <div className="flex items-center gap-2">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm text-purple-600 dark:text-purple-400">Processing...</span>
            </div>
          </div>
        )}
      </div>

      {/* Footer Stats */}
      {steps.length > 0 && (
        <div className="flex-shrink-0 p-3 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>
              {steps.filter(s => s.status === 'complete').length}/{steps.length} steps
            </span>
            <span>
              {steps.reduce((acc, s) => acc + (s.duration || 0), 0)}ms total
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

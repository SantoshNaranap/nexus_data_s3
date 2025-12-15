import { useState, useEffect } from 'react'

interface ThinkingIndicatorProps {
  content: string
  isExpanded?: boolean
  onToggle?: () => void
}

// Get a short summary (first line or first ~60 chars) for the collapsed header
function getThinkingSummary(content: string): string {
  if (!content) return 'Thought process'
  // Get first sentence or first 80 chars
  const firstLine = content.split('\n')[0]
  const firstSentence = firstLine.split(/[.!?]/)[0]
  if (firstSentence.length <= 80) {
    return firstSentence + (firstLine.length > firstSentence.length ? '...' : '')
  }
  return firstSentence.substring(0, 77) + '...'
}

export default function ThinkingIndicator({
  content,
  isExpanded: controlledExpanded,
  onToggle
}: ThinkingIndicatorProps) {
  const [internalExpanded, setInternalExpanded] = useState(false)

  // Support both controlled and uncontrolled modes
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded
  const handleToggle = onToggle || (() => setInternalExpanded(!internalExpanded))

  const summary = getThinkingSummary(content)

  return (
    <div className="mb-3">
      <button
        onClick={handleToggle}
        className="flex items-center gap-2 px-3 py-2 w-full text-left bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 transition-all duration-200"
      >
        {/* Thinking icon */}
        <div className="relative w-5 h-5 flex items-center justify-center flex-shrink-0">
          <svg
            className="w-4 h-4 text-gray-500 dark:text-gray-400"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z" />
          </svg>
        </div>

        <span className="text-sm text-gray-600 dark:text-gray-300 flex-1 truncate italic">
          {summary}
        </span>

        {/* Chevron indicator */}
        <svg
          className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expandable content area */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isExpanded ? 'max-h-[500px] opacity-100 mt-2' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/30 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-400 overflow-y-auto max-h-[400px]">
          <div className="whitespace-pre-wrap leading-relaxed">
            {content}
          </div>
        </div>
      </div>
    </div>
  )
}

// Witty thinking messages
const wittyThinkingMessages = [
  "Pondering the mysteries of your data...",
  "Consulting the digital oracle...",
  "Teaching neurons to dance...",
  "Brewing insights from raw bytes...",
  "Translating human to machine and back...",
  "Finding needles in data haystacks...",
  "Running thoughts through the neural blender...",
  "Channeling inner data wizard...",
  "Connecting the dots at light speed...",
  "Summoning the power of context...",
]

// Streaming version that shows during active thinking - shows real Claude thinking
export function ThinkingIndicatorStreaming({ content, isActive = true }: { content: string; isActive?: boolean }) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [wittyIndex, setWittyIndex] = useState(0)

  // Rotate through witty messages when actively thinking and no content yet
  useEffect(() => {
    if (!isActive || content) return

    // Start with random message
    setWittyIndex(Math.floor(Math.random() * wittyThinkingMessages.length))

    const interval = setInterval(() => {
      setWittyIndex(prev => (prev + 1) % wittyThinkingMessages.length)
    }, 2500)

    return () => clearInterval(interval)
  }, [isActive, content])

  // Get a summary for the header - use witty message if no content
  const summary = content
    ? getThinkingSummary(content)
    : wittyThinkingMessages[wittyIndex]

  return (
    <div className="mb-3 animate-fadeIn">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 px-3 py-2 w-full text-left bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 dark:hover:bg-amber-900/30 rounded-lg border border-amber-200 dark:border-amber-800/50 transition-all duration-200"
      >
        {/* Animated thinking icon */}
        <div className="relative w-5 h-5 flex items-center justify-center flex-shrink-0">
          {isActive ? (
            // Pulsing animation when actively thinking
            <div className="relative">
              <svg
                className="w-4 h-4 text-amber-500 dark:text-amber-400 animate-pulse"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z" />
              </svg>
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-amber-400 rounded-full animate-ping" />
            </div>
          ) : (
            <svg
              className="w-4 h-4 text-amber-500 dark:text-amber-400"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z" />
            </svg>
          )}
        </div>

        <span className="text-sm text-amber-700 dark:text-amber-300 flex-1 truncate italic">
          {summary}
        </span>

        {/* Chevron indicator */}
        <svg
          className={`w-4 h-4 text-amber-400 flex-shrink-0 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expandable content area with live streaming text */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isExpanded ? 'max-h-[500px] opacity-100 mt-2' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="px-4 py-3 bg-amber-50/50 dark:bg-amber-900/10 rounded-lg border border-amber-200 dark:border-amber-800/30 text-sm text-amber-800 dark:text-amber-200/90 overflow-y-auto max-h-[400px]">
          <div className="whitespace-pre-wrap leading-relaxed">
            {content || 'Analyzing your request...'}
            {/* Blinking cursor at the end when actively thinking */}
            {isActive && (
              <span className="inline-block w-0.5 h-4 bg-amber-500 dark:bg-amber-400 animate-pulse ml-0.5 align-middle" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

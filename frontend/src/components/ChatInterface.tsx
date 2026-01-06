import { useState } from 'react'
import type { DataSource } from '../types'
import { useChat } from '../hooks/useChat'
import ChatHeader from './ChatHeader'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import EmptyState from './EmptyState'
import AgentActivityPanel from './AgentActivityPanel'

interface ChatInterfaceProps {
  datasource: DataSource
}

export default function ChatInterface({ datasource }: ChatInterfaceProps) {
  const [showAgentPanel, setShowAgentPanel] = useState(true)

  const {
    messages,
    input,
    setInput,
    sessionId,
    isStreaming,
    streamingMessage,
    agentSteps,
    thinkingContent,
    isActivelyThinking,
    handleSubmit,
    handleNewConversation,
    handleFollowUpClick,
  } = useChat({ datasource })

  return (
    <div className="flex-1 flex h-full overflow-hidden bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <ChatHeader
          datasource={datasource}
          sessionId={sessionId}
          showAgentPanel={showAgentPanel}
          hasMessages={messages.length > 0}
          isStreaming={isStreaming}
          onToggleAgentPanel={() => setShowAgentPanel(!showAgentPanel)}
          onNewConversation={handleNewConversation}
        />

        {/* Messages */}
        {messages.length === 0 && !isStreaming ? (
          <div className="flex-1 overflow-y-auto p-6">
            <EmptyState datasource={datasource} />
          </div>
        ) : (
          <MessageList
            messages={messages}
            streamingMessage={streamingMessage}
            thinkingContent={thinkingContent}
            isActivelyThinking={isActivelyThinking}
            isStreaming={isStreaming}
            onFollowUpClick={handleFollowUpClick}
          />
        )}

        <MessageInput
          input={input}
          setInput={setInput}
          isStreaming={isStreaming}
          datasource={datasource}
          onSubmit={handleSubmit}
        />
      </div>

      {/* Agent Activity Panel */}
      {showAgentPanel && (
        <AgentActivityPanel
          steps={agentSteps}
          isActive={isStreaming}
          currentThought={undefined}
          onClose={() => setShowAgentPanel(false)}
        />
      )}
    </div>
  )
}

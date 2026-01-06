import type { DataSource } from '../types'

interface EmptyStateProps {
  datasource: DataSource
}

const EXAMPLE_QUERIES: Record<string, string[]> = {
  mysql: ['"Show me the latest users"', '"How many rows are in the orders table?"'],
  s3: ['"What buckets do I have?"', '"Show me files in my bucket"'],
  google_workspace: ['"Show me my recent Google Docs"', '"List my spreadsheets"', '"What\'s on my calendar today?"'],
  jira: ['"Show me my open issues"', '"What\'s in the backlog?"'],
  github: ['"Show me my repositories"', '"List open pull requests"'],
  slack: ['"What channels do I have?"', '"Show team members"'],
}

export default function EmptyState({ datasource }: EmptyStateProps) {
  const examples = EXAMPLE_QUERIES[datasource.id] || ['"Ask me anything..."']

  return (
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
          {examples.map((example, idx) => (
            <p key={idx}>{example}</p>
          ))}
        </div>
      </div>
    </div>
  )
}

import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

/**
 * Error boundary component to catch and handle React rendering errors.
 *
 * Prevents the entire app from crashing when a component throws an error.
 * Displays a fallback UI and optionally reports errors to a logging service.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo })

    // Log error to console in development
    console.error('ErrorBoundary caught an error:', error, errorInfo)

    // Call optional error handler (for logging to external service)
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }
  }

  handleRetry = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
  }

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default error UI
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mb-6">
            <svg
              className="w-8 h-8 text-red-600 dark:text-red-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>

          <h2 className="text-xl font-medium text-gray-900 dark:text-white mb-2">
            Something went wrong
          </h2>

          <p className="text-gray-600 dark:text-gray-400 text-center mb-6 max-w-md">
            An unexpected error occurred. Please try again or refresh the page.
          </p>

          <div className="flex gap-4">
            <button
              onClick={this.handleRetry}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              Try Again
            </button>

            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg transition-colors"
            >
              Refresh Page
            </button>
          </div>

          {/* Show error details in development */}
          {import.meta.env.DEV && this.state.error && (
            <details className="mt-6 p-4 bg-gray-100 dark:bg-gray-800 rounded-lg text-sm text-left max-w-2xl w-full overflow-auto">
              <summary className="cursor-pointer text-gray-700 dark:text-gray-300 font-medium mb-2">
                Error Details (Development Only)
              </summary>
              <pre className="text-red-600 dark:text-red-400 whitespace-pre-wrap break-words">
                {this.state.error.toString()}
              </pre>
              {this.state.errorInfo && (
                <pre className="mt-2 text-gray-600 dark:text-gray-400 whitespace-pre-wrap break-words text-xs">
                  {this.state.errorInfo.componentStack}
                </pre>
              )}
            </details>
          )}
        </div>
      )
    }

    return this.props.children
  }
}

/**
 * Specialized error boundary for chat interface.
 * Shows a more contextual error message for chat-related errors.
 */
export function ChatErrorBoundary({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary
      fallback={
        <div className="flex flex-col items-center justify-center h-full p-8">
          <div className="w-12 h-12 bg-orange-100 dark:bg-orange-900/30 rounded-full flex items-center justify-center mb-4">
            <svg
              className="w-6 h-6 text-orange-600 dark:text-orange-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <p className="text-gray-600 dark:text-gray-400 text-center mb-4">
            Failed to load chat interface
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
          >
            Reload
          </button>
        </div>
      }
    >
      {children}
    </ErrorBoundary>
  )
}

/**
 * Error boundary for sidebar components.
 */
export function SidebarErrorBoundary({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary
      fallback={
        <div className="p-4 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
            Failed to load sidebar
          </p>
          <button
            onClick={() => window.location.reload()}
            className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
          >
            Refresh
          </button>
        </div>
      }
    >
      {children}
    </ErrorBoundary>
  )
}

export default ErrorBoundary

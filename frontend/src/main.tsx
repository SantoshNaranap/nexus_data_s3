import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

console.log('[Mosaic] Starting app...')

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

try {
  const rootElement = document.getElementById('root')
  console.log('[Mosaic] Root element:', rootElement)

  if (rootElement) {
    ReactDOM.createRoot(rootElement).render(
      <React.StrictMode>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </React.StrictMode>,
    )
    console.log('[Mosaic] App rendered successfully')
  } else {
    console.error('[Mosaic] Root element not found!')
  }
} catch (error) {
  console.error('[Mosaic] Error rendering app:', error)
}

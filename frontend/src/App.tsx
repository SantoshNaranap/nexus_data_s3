import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { datasourceApi, credentialsApi } from './services/api'
import DataSourceSidebar from './components/DataSourceSidebar'
import ChatInterface from './components/ChatInterface'
import SettingsPanel from './components/SettingsPanel'
import UserMenu from './components/UserMenu'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import type { DataSource } from './types'

function AppContent() {
  const [selectedDatasource, setSelectedDatasource] = useState<DataSource | null>(null)
  const [configuredDatasources, setConfiguredDatasources] = useState<Set<string>>(new Set())
  const [settingsPanelOpen, setSettingsPanelOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const { user: _user, isAuthenticated } = useAuth()

  const { data: datasources, isLoading } = useQuery({
    queryKey: ['datasources'],
    queryFn: datasourceApi.list,
  })

  // Check which datasources already have credentials saved
  useEffect(() => {
    async function checkExistingCredentials() {
      if (!datasources || !isAuthenticated) return

      const configured = new Set<string>()

      // Check each datasource for existing credentials
      await Promise.all(
        datasources.map(async (ds) => {
          try {
            const status = await credentialsApi.checkStatus(ds.id)
            if (status.configured) {
              configured.add(ds.id)
              console.log(`[App] ${ds.id} already configured`)
            }
          } catch (error) {
            console.error(`[App] Failed to check ${ds.id} credentials:`, error)
          }
        })
      )

      setConfiguredDatasources(configured)
      console.log('[App] Configured datasources:', Array.from(configured))
    }

    checkExistingCredentials()
  }, [datasources, isAuthenticated])

  const handleSelectDatasource = (datasource: DataSource) => {
    setSelectedDatasource(datasource)
  }

  const handleSaveCredentials = async (
    datasource: string,
    credentials: Record<string, string>,
    testResult?: { success: boolean }
  ) => {
    try {
      // Send credentials to backend using the API service
      await credentialsApi.save(datasource, credentials)

      // Only mark as configured if test result is successful
      if (testResult?.success) {
        setConfiguredDatasources((prev) => new Set(prev).add(datasource))
      } else if (testResult?.success === false) {
        // Remove from configured if test failed
        setConfiguredDatasources((prev) => {
          const updated = new Set(prev)
          updated.delete(datasource)
          return updated
        })
      }
    } catch (error) {
      console.error('Error saving credentials:', error)
      throw error
    }
  }

  return (
    <div className="flex h-screen bg-white dark:bg-gray-900 text-gray-900 dark:text-white transition-colors duration-200">
      <DataSourceSidebar
        datasources={datasources || []}
        selectedDatasource={selectedDatasource}
        onSelectDatasource={handleSelectDatasource}
        onOpenSettings={() => setSettingsPanelOpen(true)}
        configuredDatasources={configuredDatasources}
        isLoading={isLoading}
      />

      {/* Settings Panel */}
      <SettingsPanel
        datasources={datasources || []}
        isOpen={settingsPanelOpen}
        onClose={() => setSettingsPanelOpen(false)}
        onSave={handleSaveCredentials}
        configuredDatasources={configuredDatasources}
      />

      <div className="flex-1 flex flex-col">
        {/* Google-style Header */}
        <header className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-6 py-4 transition-colors duration-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg flex items-center justify-center shadow-lg">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-xl font-normal text-gray-700 dark:text-gray-200">
                    Mosaic
                  </h1>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    by Kaay
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Theme Toggle - Google style */}
              <button
                onClick={toggleTheme}
                className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-all duration-200"
                aria-label="Toggle theme"
              >
                {theme === 'light' ? (
                  <svg className="w-5 h-5 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                )}
              </button>

              {/* User Menu */}
              <UserMenu />
            </div>
          </div>
        </header>

        {selectedDatasource ? (
          <ChatInterface datasource={selectedDatasource} />
        ) : (
          <div className="flex-1 flex items-center justify-center p-8 bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
            <div className="text-center max-w-3xl">
              {/* Google-style illustration */}
              <div className="mb-8">
                <div className="w-32 h-32 mx-auto bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center shadow-2xl">
                  <svg className="w-16 h-16 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
              </div>

              <h2 className="text-4xl font-normal mb-3 text-gray-900 dark:text-white">
                Welcome to Mosaic
              </h2>
              <p className="text-lg text-gray-600 dark:text-gray-400 mb-12">
                Your unified interface for all data sources
              </p>

              {/* Google-style feature cards */}
              <div className="grid grid-cols-2 gap-6 text-left max-w-2xl mx-auto">
                <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-all duration-200">
                  <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <h3 className="font-medium text-gray-900 dark:text-white mb-2">Natural Language</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Ask questions in plain English</p>
                </div>

                <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-all duration-200">
                  <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <h3 className="font-medium text-gray-900 dark:text-white mb-2">Real-time Streaming</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Get instant responses</p>
                </div>

                <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-all duration-200">
                  <div className="w-12 h-12 bg-purple-100 dark:bg-purple-900/30 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </div>
                  <h3 className="font-medium text-gray-900 dark:text-white mb-2">Context Switching</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Switch sources seamlessly</p>
                </div>

                <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-all duration-200">
                  <div className="w-12 h-12 bg-orange-100 dark:bg-orange-900/30 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-orange-600 dark:text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <h3 className="font-medium text-gray-900 dark:text-white mb-2">AI-Powered</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Powered by Claude Sonnet 4.5</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function MainApp() {
  return (
    <ProtectedRoute>
      <AppContent />
    </ProtectedRoute>
  )
}

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<MainApp />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}

export default App

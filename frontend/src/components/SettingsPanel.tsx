import { useState } from 'react'
import type { DataSource } from '../types'
import { datasourceApi } from '../services/api'
import DataSourceIcon from './DataSourceIcon'

interface SettingsPanelProps {
  datasources: DataSource[]
  isOpen: boolean
  onClose: () => void
  onSave: (datasource: string, credentials: Record<string, string>, testResult?: { success: boolean }) => void
  configuredDatasources: Set<string>
}

interface CredentialField {
  name: string
  label: string
  type: 'text' | 'password'
  placeholder: string
  required: boolean
}

// Instructions for obtaining API credentials for each datasource
const credentialInstructions: Record<string, { title: string; steps: string[] }> = {
  s3: {
    title: 'How to get AWS credentials',
    steps: [
      'Log in to AWS Console at aws.amazon.com',
      'Go to IAM → Users → Your user → Security credentials',
      'Click "Create access key" and select your use case',
      'Copy the Access Key ID and Secret Access Key',
      'For region, use your S3 bucket\'s region (e.g., us-east-1)',
    ],
  },
  mysql: {
    title: 'How to get MySQL credentials',
    steps: [
      'Host: Your database server address (e.g., localhost or AWS RDS endpoint)',
      'Port: Usually 3306 for MySQL',
      'Username/Password: Provided by your database administrator',
      'Database: The specific database name you want to connect to',
    ],
  },
  jira: {
    title: 'How to get JIRA API Token',
    steps: [
      'Log in to Atlassian at id.atlassian.com',
      'Go to Security → Create and manage API tokens',
      'Click "Create API token" and give it a label',
      'Copy the token (shown only once)',
      'URL format: https://your-company.atlassian.net',
    ],
  },
  shopify: {
    title: 'How to get Shopify Access Token',
    steps: [
      'Log in to your Shopify admin panel',
      'Go to Settings → Apps and sales channels → Develop apps',
      'Create an app or select existing one',
      'Go to API credentials and create Admin API access token',
      'Shop URL format: your-store.myshopify.com',
    ],
  },
  google_workspace: {
    title: 'How to get Google OAuth credentials',
    steps: [
      'Go to Google Cloud Console (console.cloud.google.com)',
      'Create a project or select existing one',
      'Enable Google Drive API and Gmail API',
      'Go to APIs & Services → Credentials → Create OAuth Client ID',
      'Set application type to "Web application"',
      'Add authorized redirect URI: http://localhost:8000/api/auth/google/callback',
    ],
  },
  slack: {
    title: 'How to get Slack Tokens',
    steps: [
      'Go to api.slack.com/apps and click "Create New App"',
      'Choose "From scratch" and select your workspace',
      'Go to OAuth & Permissions in the sidebar',
      'Add Bot scopes: channels:read, channels:history, chat:write, users:read',
      'Add User scopes: channels:read, channels:history, im:read, im:history, search:read',
      'Click "Install to Workspace" and authorize',
      'Copy "Bot User OAuth Token" (xoxb-) → Bot Token field',
      'Copy "User OAuth Token" (xoxp-) → User Token field',
      '⚠️ IMPORTANT: User Token is REQUIRED to access private channels!',
    ],
  },
}

const credentialFields: Record<string, CredentialField[]> = {
  s3: [
    {
      name: 'aws_access_key_id',
      label: 'AWS Access Key ID',
      type: 'text',
      placeholder: 'AKIAIOSFODNN7EXAMPLE',
      required: true,
    },
    {
      name: 'aws_secret_access_key',
      label: 'AWS Secret Access Key',
      type: 'password',
      placeholder: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
      required: true,
    },
    {
      name: 'aws_default_region',
      label: 'AWS Region',
      type: 'text',
      placeholder: 'us-east-1',
      required: false,
    },
  ],
  mysql: [
    {
      name: 'mysql_host',
      label: 'Host',
      type: 'text',
      placeholder: 'localhost',
      required: true,
    },
    {
      name: 'mysql_port',
      label: 'Port',
      type: 'text',
      placeholder: '3306',
      required: true,
    },
    {
      name: 'mysql_user',
      label: 'Username',
      type: 'text',
      placeholder: 'root',
      required: true,
    },
    {
      name: 'mysql_password',
      label: 'Password',
      type: 'password',
      placeholder: '',
      required: true,
    },
    {
      name: 'mysql_database',
      label: 'Database',
      type: 'text',
      placeholder: 'mydb',
      required: true,
    },
  ],
  jira: [
    {
      name: 'jira_url',
      label: 'JIRA URL',
      type: 'text',
      placeholder: 'https://your-domain.atlassian.net',
      required: true,
    },
    {
      name: 'jira_email',
      label: 'Email',
      type: 'text',
      placeholder: 'you@example.com',
      required: true,
    },
    {
      name: 'jira_api_token',
      label: 'API Token',
      type: 'password',
      placeholder: 'Your JIRA API token',
      required: true,
    },
  ],
  shopify: [
    {
      name: 'shopify_shop_url',
      label: 'Shop URL',
      type: 'text',
      placeholder: 'your-store.myshopify.com',
      required: true,
    },
    {
      name: 'shopify_access_token',
      label: 'Access Token',
      type: 'password',
      placeholder: 'shpat_...',
      required: true,
    },
    {
      name: 'shopify_api_version',
      label: 'API Version',
      type: 'text',
      placeholder: '2024-01',
      required: false,
    },
  ],
  google_workspace: [
    {
      name: 'google_oauth_client_id',
      label: 'OAuth Client ID',
      type: 'text',
      placeholder: 'your-client-id.apps.googleusercontent.com',
      required: true,
    },
    {
      name: 'google_oauth_client_secret',
      label: 'OAuth Client Secret',
      type: 'password',
      placeholder: 'GOCSPX-...',
      required: true,
    },
    {
      name: 'user_google_email',
      label: 'Google Email (Optional)',
      type: 'text',
      placeholder: 'you@gmail.com',
      required: false,
    },
  ],
  slack: [
    {
      name: 'slack_bot_token',
      label: 'Bot Token (xoxb-)',
      type: 'password',
      placeholder: 'xoxb-...',
      required: true,
    },
    {
      name: 'slack_user_token',
      label: 'User Token (xoxp-) - Required for Private Channels & DMs',
      type: 'password',
      placeholder: 'xoxp-...',
      required: false,
    },
    {
      name: 'slack_app_token',
      label: 'App Token (Optional)',
      type: 'password',
      placeholder: 'xapp-...',
      required: false,
    },
  ],
}


export default function SettingsPanel({
  datasources,
  isOpen,
  onClose,
  onSave,
  configuredDatasources,
}: SettingsPanelProps) {
  const [selectedDatasource, setSelectedDatasource] = useState<DataSource | null>(
    datasources[0] || null
  )
  const [credentials, setCredentials] = useState<Record<string, Record<string, string>>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [testing, setTesting] = useState<Record<string, boolean>>({})
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({})

  if (!isOpen) return null

  const handleSave = async (datasourceId: string) => {
    const fields = credentialFields[datasourceId] || []
    const datasourceCredentials = credentials[datasourceId] || {}

    // Validate required fields
    const newErrors: Record<string, string> = {}
    fields.forEach((field) => {
      if (field.required && !datasourceCredentials[field.name]?.trim()) {
        newErrors[`${datasourceId}_${field.name}`] = `${field.label} is required`
      }
    })

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    // Clear previous test results
    setTestResults((prev) => {
      const updated = { ...prev }
      delete updated[datasourceId]
      return updated
    })

    // Set testing state
    setTesting((prev) => ({ ...prev, [datasourceId]: true }))

    try {
      // Save credentials first
      await onSave(datasourceId, datasourceCredentials)

      // Test the connection using the API service
      const testResult = await datasourceApi.test(datasourceId)

      if (testResult.connected) {
        const successResult = {
          success: true,
          message: 'Connection successful! Credentials verified.',
        }

        setTestResults((prev) => ({
          ...prev,
          [datasourceId]: successResult,
        }))

        // Notify parent of successful test
        await onSave(datasourceId, datasourceCredentials, { success: true })

        // Keep credentials in form so user can see what was saved
        // (passwords are masked anyway for security)
      } else {
        const failureResult = {
          success: false,
          message: testResult.error || 'Connection failed. Please check your credentials.',
        }

        setTestResults((prev) => ({
          ...prev,
          [datasourceId]: failureResult,
        }))

        // Notify parent of failed test
        await onSave(datasourceId, datasourceCredentials, { success: false })
      }
    } catch (error) {
      const errorResult = {
        success: false,
        message: error instanceof Error ? error.message : 'Failed to test connection',
      }

      setTestResults((prev) => ({
        ...prev,
        [datasourceId]: errorResult,
      }))

      // Notify parent of failed test
      try {
        await onSave(datasourceId, datasourceCredentials, { success: false })
      } catch (saveError) {
        // Ignore save error if it already failed
      }
    } finally {
      setTesting((prev) => ({ ...prev, [datasourceId]: false }))
    }
  }

  const handleChange = (datasourceId: string, fieldName: string, value: string) => {
    setCredentials((prev) => ({
      ...prev,
      [datasourceId]: {
        ...(prev[datasourceId] || {}),
        [fieldName]: value,
      },
    }))
    setErrors((prev) => {
      const updated = { ...prev }
      delete updated[`${datasourceId}_${fieldName}`]
      return updated
    })
  }

  const handleClose = () => {
    setCredentials({})
    setErrors({})
    onClose()
  }

  const currentFields = selectedDatasource ? credentialFields[selectedDatasource.id] || [] : []
  const currentCredentials = selectedDatasource ? credentials[selectedDatasource.id] || {} : {}
  const isConfigured = selectedDatasource ? configuredDatasources.has(selectedDatasource.id) : false
  const isTesting = selectedDatasource ? testing[selectedDatasource.id] || false : false
  const testResult = selectedDatasource ? testResults[selectedDatasource.id] : null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden shadow-2xl flex">
        {/* Sidebar - Datasource List */}
        <div className="w-64 border-r border-gray-200 dark:border-gray-700 flex flex-col">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Settings</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Configure your connectors
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            {datasources.map((datasource) => (
              <button
                key={datasource.id}
                onClick={() => setSelectedDatasource(datasource)}
                className={`w-full text-left p-3 rounded-lg mb-2 transition-all ${
                  selectedDatasource?.id === datasource.id
                    ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-500'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <DataSourceIcon datasourceId={datasource.id} size={24} />
                    <span className={`text-sm font-medium ${
                      selectedDatasource?.id === datasource.id
                        ? 'text-blue-700 dark:text-blue-400'
                        : 'text-gray-900 dark:text-white'
                    }`}>
                      {datasource.name}
                    </span>
                  </div>
                  {configuredDatasources.has(datasource.id) && (
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  )}
                </div>
              </button>
            ))}
          </div>

          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={handleClose}
              className="w-full px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors text-sm"
            >
              Close
            </button>
          </div>
        </div>

        {/* Main Content - Credential Form */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedDatasource ? (
            <>
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <DataSourceIcon datasourceId={selectedDatasource.id} size={36} />
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                        {selectedDatasource.name}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {selectedDatasource.description}
                      </p>
                    </div>
                  </div>
                  {isConfigured && (
                    <div className="flex items-center text-sm text-green-600 dark:text-green-400">
                      <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
                      Configured
                    </div>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-4 max-w-2xl">
                  {currentFields.map((field) => (
                    <div key={field.name}>
                      <label
                        htmlFor={field.name}
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
                      >
                        {field.label}
                        {field.required && <span className="text-red-500 ml-1">*</span>}
                      </label>
                      <input
                        type={field.type}
                        id={field.name}
                        value={currentCredentials[field.name] || ''}
                        onChange={(e) =>
                          handleChange(selectedDatasource.id, field.name, e.target.value)
                        }
                        placeholder={field.placeholder}
                        className={`w-full px-4 py-2 bg-gray-50 dark:bg-gray-900 border ${
                          errors[`${selectedDatasource.id}_${field.name}`]
                            ? 'border-red-500 dark:border-red-500'
                            : 'border-gray-300 dark:border-gray-600'
                        } rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-white transition-colors`}
                      />
                      {errors[`${selectedDatasource.id}_${field.name}`] && (
                        <p className="text-red-500 text-sm mt-1">
                          {errors[`${selectedDatasource.id}_${field.name}`]}
                        </p>
                      )}
                    </div>
                  ))}

                  {/* Test Result */}
                  {testResult && (
                    <div
                      className={`rounded-lg p-4 mt-6 ${
                        testResult.success
                          ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                          : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                      }`}
                    >
                      <div className="flex items-start space-x-3">
                        {testResult.success ? (
                          <svg
                            className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                          </svg>
                        ) : (
                          <svg
                            className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                          </svg>
                        )}
                        <div
                          className={`text-sm ${
                            testResult.success
                              ? 'text-green-900 dark:text-green-200'
                              : 'text-red-900 dark:text-red-200'
                          }`}
                        >
                          <p className="font-medium mb-1">
                            {testResult.success ? 'Connection Successful' : 'Connection Failed'}
                          </p>
                          <p>{testResult.message}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Credential Instructions */}
                  {credentialInstructions[selectedDatasource.id] && (
                    <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4 mt-6">
                      <div className="flex items-start space-x-3">
                        <svg
                          className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                          />
                        </svg>
                        <div className="text-sm text-amber-900 dark:text-amber-200">
                          <p className="font-medium mb-2">{credentialInstructions[selectedDatasource.id].title}</p>
                          <ol className="list-decimal list-inside space-y-1">
                            {credentialInstructions[selectedDatasource.id].steps.map((step, index) => (
                              <li key={index} className="text-amber-800 dark:text-amber-300">{step}</li>
                            ))}
                          </ol>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mt-4">
                    <div className="flex items-start space-x-3">
                      <svg
                        className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                      <div className="text-sm text-blue-900 dark:text-blue-200">
                        <p className="font-medium mb-1">Secure Storage</p>
                        <p>
                          Your credentials are encrypted and stored securely in the database.
                          They persist across sessions and you only need to enter them once per datasource.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-6 border-t border-gray-200 dark:border-gray-700">
                <div className="flex justify-end">
                  <button
                    onClick={() => handleSave(selectedDatasource.id)}
                    disabled={isTesting}
                    className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white rounded-lg transition-colors shadow-sm hover:shadow-md flex items-center space-x-2"
                  >
                    {isTesting ? (
                      <>
                        <svg
                          className="w-5 h-5 animate-spin"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          />
                        </svg>
                        <span>Testing Connection...</span>
                      </>
                    ) : (
                      <span>Save & Test Connection</span>
                    )}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400">
              Select a connector to configure
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

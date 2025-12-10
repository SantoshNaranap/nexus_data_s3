/**
 * Centralized constants for the application
 */

// Data source icons - single source of truth
export const DATA_SOURCE_ICONS: Record<string, string> = {
  s3: '🪣',
  mysql: '🐬',
  jira: '📋',
  shopify: '🛍️',
  google_workspace: '📝',
  slack: '💬',
  github: '🐙',
}

// Helper function to get icon with fallback
export const getDataSourceIcon = (datasourceId: string): string => {
  return DATA_SOURCE_ICONS[datasourceId] || '📦'
}

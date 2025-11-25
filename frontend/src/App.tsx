import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { datasourceApi } from './services/api'
import DataSourceSidebar from './components/DataSourceSidebar'
import ChatInterface from './components/ChatInterface'
import type { DataSource } from './types'

function App() {
  const [selectedDatasource, setSelectedDatasource] = useState<DataSource | null>(null)

  const { data: datasources, isLoading } = useQuery({
    queryKey: ['datasources'],
    queryFn: datasourceApi.list,
  })

  const handleSelectDatasource = (datasource: DataSource) => {
    setSelectedDatasource(datasource)
  }

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      <DataSourceSidebar
        datasources={datasources || []}
        selectedDatasource={selectedDatasource}
        onSelectDatasource={handleSelectDatasource}
        isLoading={isLoading}
      />

      <div className="flex-1 flex flex-col">
        <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
          <h1 className="text-2xl font-bold">ConnectorMCP</h1>
          <p className="text-sm text-gray-400 mt-1">
            Multi-Source Data Connector with Natural Language Interface
          </p>
        </header>

        {selectedDatasource ? (
          <ChatInterface datasource={selectedDatasource} />
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-6xl mb-4">💬</div>
              <h2 className="text-xl font-semibold mb-2">Welcome to ConnectorMCP</h2>
              <p className="text-gray-400">
                Select a data source from the sidebar to start chatting
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App

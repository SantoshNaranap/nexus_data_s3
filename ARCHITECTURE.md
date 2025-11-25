# ConnectorMCP - Multi-Source Data Connector Architecture

## Overview

ConnectorMCP is a production-level application that enables natural language interaction with multiple data sources (Amazon S3, MySQL, JIRA, Shopify) through the Model Context Protocol (MCP). The application features a modular architecture with independent, reusable connector services.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend Layer                           │
│  ┌────────────────────────────────────────────────────┐    │
│  │  React + TypeScript Chat Interface                  │    │
│  │  - Data source selector sidebar                     │    │
│  │  - Chat interface for natural language queries      │    │
│  │  - Real-time response streaming                     │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ REST API / WebSocket
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend Service Layer                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │  FastAPI Application                                │    │
│  │  - API endpoints for chat queries                   │    │
│  │  - MCP client orchestration                         │    │
│  │  - Anthropic Claude integration                     │    │
│  │  - Session management                               │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ MCP Protocol (stdio)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   MCP Connector Layer                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   S3     │  │  MySQL   │  │   JIRA   │  │ Shopify  │  │
│  │  Server  │  │  Server  │  │  Server  │  │  Server  │  │
│  │          │  │          │  │          │  │          │  │
│  │ - List   │  │ - Query  │  │ - Issues │  │ - Orders │  │
│  │ - Read   │  │ - Schema │  │ - Search │  │ - Products│ │
│  │ - Write  │  │ - Execute│  │ - Update │  │ - Search │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Native SDKs/APIs
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Source Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Amazon   │  │  MySQL   │  │   JIRA   │  │ Shopify  │  │
│  │    S3    │  │ Database │  │   API    │  │   API    │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Frontend (React + TypeScript)

**Location**: `/frontend`

**Responsibilities**:
- Render chat interface with message history
- Display data source selector sidebar
- Handle user input and streaming responses
- Manage UI state and session persistence

**Key Technologies**:
- React 18+ with TypeScript
- Vite for build tooling
- TanStack Query for API state management
- WebSocket for real-time communication
- Tailwind CSS for styling

### 2. Backend Service (Python FastAPI)

**Location**: `/backend`

**Responsibilities**:
- Expose REST API for chat operations
- Orchestrate MCP client connections
- Integrate with Anthropic Claude API
- Handle authentication and session management
- Route queries to appropriate MCP servers
- Transform LLM responses into user-friendly formats

**Key Technologies**:
- FastAPI for API framework
- Pydantic for data validation
- MCP Python SDK for MCP client
- Anthropic SDK for Claude integration
- pytest for testing
- uvicorn for ASGI server

**API Endpoints**:
```
POST   /api/chat/message          - Send chat message
GET    /api/chat/sessions         - List chat sessions
POST   /api/chat/sessions         - Create new session
GET    /api/datasources           - List available data sources
GET    /api/datasources/:id/test  - Test data source connection
```

### 3. MCP Connector Services

Each connector is an independent MCP server that can be:
- Run as a standalone service
- Exported and used in other applications
- Tested independently
- Deployed separately

#### S3 Connector (`/connectors/s3`)

**Tools**:
- `list_buckets` - List all S3 buckets
- `list_objects` - List objects in a bucket
- `read_object` - Read object content
- `write_object` - Write/upload object
- `search_objects` - Search objects by prefix/pattern

**Resources**:
- Bucket metadata
- Object listings
- File contents

#### MySQL Connector (`/connectors/mysql`)

**Tools**:
- `list_databases` - List all databases
- `list_tables` - List tables in a database
- `describe_table` - Get table schema
- `execute_query` - Execute SELECT queries
- `get_table_stats` - Get row counts and statistics

**Resources**:
- Database schemas
- Table metadata
- Query results

#### JIRA Connector (`/connectors/jira`)

**Tools**:
- `search_issues` - Search issues using JQL
- `get_issue` - Get issue details
- `create_issue` - Create new issue
- `update_issue` - Update issue fields
- `list_projects` - List all projects
- `get_project` - Get project details

**Resources**:
- Issue data
- Project information
- User assignments

#### Shopify Connector (`/connectors/shopify`)

**Tools**:
- `list_products` - List all products
- `get_product` - Get product details
- `search_products` - Search products
- `list_orders` - List orders
- `get_order` - Get order details
- `get_inventory` - Get inventory levels

**Resources**:
- Product catalog
- Order history
- Inventory data

## Data Flow

### Query Processing Flow

1. **User Input**: User types natural language query in chat interface
2. **Frontend**: Sends query + selected data source to backend API
3. **Backend**:
   - Receives query
   - Initializes MCP client for selected data source
   - Constructs Claude API request with MCP tools available
4. **Claude LLM**:
   - Analyzes query
   - Determines which MCP tools to call
   - Makes tool calls through MCP protocol
5. **MCP Server**:
   - Executes tool call against data source
   - Returns structured results
6. **Backend**:
   - Receives tool results
   - Sends back to Claude for interpretation
   - Claude generates natural language response
7. **Frontend**: Displays response to user

### Example Query Flow

```
User: "Show me all orders from last week"
  ↓
Frontend: POST /api/chat/message {query: "...", datasource: "shopify"}
  ↓
Backend: Initialize Shopify MCP client
  ↓
Claude: Interprets query → calls list_orders tool with date filter
  ↓
Shopify MCP Server: Fetches orders from Shopify API
  ↓
Backend: Receives results → sends to Claude
  ↓
Claude: Formats response naturally
  ↓
Frontend: Displays "I found 47 orders from last week..."
```

## Technology Stack

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **State Management**: TanStack Query + React Context
- **Styling**: Tailwind CSS
- **Testing**: Jest + React Testing Library
- **API Client**: Axios

### Backend
- **Framework**: Python 3.11+ with FastAPI
- **MCP SDK**: mcp Python package
- **LLM**: Anthropic Claude SDK
- **Data Validation**: Pydantic v2
- **Testing**: pytest + pytest-asyncio
- **Server**: uvicorn (ASGI)

### MCP Connectors
- **Runtime**: Python 3.11+
- **MCP SDK**: mcp Python package
- **AWS SDK**: boto3 (S3)
- **Database**: mysql-connector-python
- **APIs**: requests + respective SDKs (jira, shopify)

### DevOps
- **Containerization**: Docker + Docker Compose
- **CI/CD**: GitHub Actions
- **Linting**: ESLint (TS), ruff (Python)
- **Formatting**: Prettier (TS), black (Python)

## Security Considerations

1. **Credential Management**:
   - Environment variables for sensitive data
   - Secret rotation support
   - No hardcoded credentials

2. **API Security**:
   - API key authentication
   - Rate limiting
   - CORS configuration

3. **Data Access**:
   - Principle of least privilege
   - Read-only by default (except where needed)
   - Audit logging

4. **MCP Communication**:
   - Stdio transport (local process isolation)
   - Input validation on all tool calls
   - Error handling without data leakage

## Testing Strategy

### Unit Tests
- All MCP tool functions
- Backend API endpoints
- Frontend components
- Utility functions

### Integration Tests
- MCP server initialization
- Tool call execution
- API request/response cycles

### End-to-End Tests
- Complete query flow
- Multiple data source switching
- Error handling scenarios

### Coverage Goals
- Backend: 80%+ coverage
- Frontend: 75%+ coverage
- MCP Connectors: 85%+ coverage

## Deployment Architecture

### Development
```
docker-compose up
├── frontend (port 5173)
├── backend (port 8000)
└── MCP servers (stdio)
```

### Production
```
Frontend: Static hosting (Vercel/Netlify)
Backend: Container service (AWS ECS/GCP Cloud Run)
MCP Servers: Bundled with backend container
Database: Managed PostgreSQL (session storage)
```

## Project Structure

```
ConnectorMCP/
├── frontend/                 # React TypeScript frontend
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── hooks/          # Custom hooks
│   │   ├── services/       # API clients
│   │   ├── types/          # TypeScript types
│   │   └── utils/          # Utility functions
│   ├── tests/              # Jest tests
│   └── package.json
│
├── backend/                  # FastAPI backend
│   ├── app/
│   │   ├── api/            # API routes
│   │   ├── core/           # Core functionality
│   │   ├── models/         # Pydantic models
│   │   ├── services/       # Business logic
│   │   └── main.py         # FastAPI app
│   ├── tests/              # pytest tests
│   └── requirements.txt
│
├── connectors/              # MCP connector services
│   ├── s3/
│   │   ├── src/
│   │   │   └── s3_server.py
│   │   ├── tests/
│   │   └── pyproject.toml
│   ├── mysql/
│   │   ├── src/
│   │   │   └── mysql_server.py
│   │   ├── tests/
│   │   └── pyproject.toml
│   ├── jira/
│   │   ├── src/
│   │   │   └── jira_server.py
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── shopify/
│       ├── src/
│       │   └── shopify_server.py
│       ├── tests/
│       └── pyproject.toml
│
├── docs/                    # Additional documentation
├── docker-compose.yml       # Local development setup
├── .env.example            # Environment variables template
└── README.md               # Setup and usage guide
```

## Extensibility

### Adding New Data Sources

1. Create new connector in `/connectors/<name>/`
2. Implement MCP server with tools and resources
3. Add tests for all tools
4. Update backend to include new connector
5. Add to frontend datasource selector
6. Document in README

### Exporting Connectors

Each connector is independent and can be exported by:
1. Copying connector directory
2. Installing dependencies from `pyproject.toml`
3. Running as standalone MCP server
4. Providing configuration via environment variables

## Performance Considerations

- **Connection Pooling**: Reuse MCP client connections
- **Caching**: Cache frequently accessed data (with TTL)
- **Streaming**: Stream LLM responses for better UX
- **Lazy Loading**: Initialize MCP servers on-demand
- **Rate Limiting**: Respect API rate limits of data sources

## Future Enhancements

1. **Vector Database Integration**: For semantic search capabilities
2. **Multi-Source Queries**: Query across multiple sources simultaneously
3. **Query History**: Store and retrieve past queries
4. **Custom Prompts**: User-defined system prompts per data source
5. **Data Visualization**: Automatic chart generation for query results
6. **Scheduled Queries**: Run queries on schedule
7. **Alerting**: Set up alerts based on query conditions
8. **Export Functionality**: Export query results to various formats

## Monitoring & Observability

- Application logs (structured JSON)
- Error tracking (Sentry integration ready)
- Performance metrics (request duration, tool call latency)
- Usage analytics (queries per data source)

## License

[To be determined]

## Maintainers

[Project team information]

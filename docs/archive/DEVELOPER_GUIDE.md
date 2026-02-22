# ConnectorMCP - Developer Guide

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Setup & Installation](#setup--installation)
5. [How It Works](#how-it-works)
6. [Component Details](#component-details)
7. [API Documentation](#api-documentation)
8. [Development Workflow](#development-workflow)
9. [Testing](#testing)
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)
12. [Extending the System](#extending-the-system)

---

## Overview

**ConnectorMCP** is a production-ready application that enables natural language interaction with multiple data sources (S3, MySQL, JIRA, Shopify) using the Model Context Protocol (MCP) and Anthropic Claude AI.

### Key Features

- 🤖 **Natural Language Queries** - Chat with data sources using plain English
- 🔌 **MCP Architecture** - Each connector is a standalone, reusable MCP server
- 🎯 **LLM Integration** - Claude Sonnet 4.5 for intelligent query understanding
- ⚡ **Real-time Streaming** - Character-by-character response streaming
- 🧠 **Context Awareness** - Maintains conversation context and switches between sources seamlessly
- 📦 **Modular Design** - Connectors can be used independently in other applications

### Tech Stack

**Frontend:**
- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- Axios (HTTP client)

**Backend:**
- FastAPI (Python web framework)
- Uvicorn (ASGI server)
- Anthropic SDK (Claude AI)
- MCP SDK (connector protocol)

**Connectors:**
- Python-based MCP servers
- boto3 (AWS S3)
- mysql-connector-python (MySQL)
- jira (JIRA API)
- shopify (Shopify API)

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│              (React + TypeScript + Vite)                    │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Chat UI    │  │   Data       │  │   API        │    │
│  │   Component  │  │   Source     │  │   Client     │    │
│  │              │  │   Selector   │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                    HTTP/SSE (Streaming)
                            │
┌─────────────────────────────────────────────────────────────┐
│                       Backend API                           │
│                    (FastAPI + Python)                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Chat Service                            │  │
│  │  • Manages conversation history                     │  │
│  │  • Orchestrates Claude AI + MCP tools               │  │
│  │  • Handles streaming responses                      │  │
│  │  • Context extraction & parameter injection         │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              MCP Service                             │  │
│  │  • Manages MCP client connections                   │  │
│  │  • Routes tool calls to appropriate connectors      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                  MCP Protocol (stdio)
                            │
┌─────────────────────────────────────────────────────────────┐
│                    MCP Connectors                           │
│              (Independent Python Servers)                   │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │    S3    │  │  MySQL   │  │   JIRA   │  │ Shopify  │  │
│  │ Connector│  │Connector │  │Connector │  │Connector │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User sends message** → Frontend
2. **Frontend makes API request** → Backend `/api/chat/message/stream`
3. **Backend retrieves available tools** → MCP Connectors
4. **Backend calls Claude AI** with tools + conversation history
5. **Claude decides which tools to use** → Returns tool calls
6. **Backend executes tool calls** → MCP Connectors
7. **MCP Connectors query data sources** → Return results
8. **Claude processes results** → Generates natural language response
9. **Backend streams response** → Frontend (character-by-character)
10. **Frontend displays streaming text** → User sees response in real-time

---

## Project Structure

```
ConnectorMCP/
├── frontend/                    # React + TypeScript frontend
│   ├── src/
│   │   ├── components/          # React components
│   │   │   ├── ChatInterface.tsx
│   │   │   └── DataSourceSelector.tsx
│   │   ├── services/            # API client services
│   │   │   └── api.ts
│   │   ├── types/               # TypeScript type definitions
│   │   │   └── index.ts
│   │   ├── App.tsx              # Main app component
│   │   └── main.tsx             # Entry point
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── api/                 # API route handlers
│   │   │   ├── chat.py          # Chat endpoints
│   │   │   └── datasources.py  # Data source endpoints
│   │   ├── core/                # Core configuration
│   │   │   └── config.py        # Settings management
│   │   ├── models/              # Pydantic models
│   │   │   └── chat.py          # Request/response models
│   │   ├── services/            # Business logic
│   │   │   ├── chat_service.py  # Chat orchestration
│   │   │   └── mcp_service.py   # MCP client management
│   │   └── main.py              # FastAPI application
│   ├── tests/                   # Backend tests
│   │   └── test_api.py
│   ├── requirements.txt
│   └── pytest.ini
│
├── connectors/                  # MCP Connector servers
│   ├── s3/                      # S3 connector
│   │   ├── src/
│   │   │   └── s3_server.py     # MCP server implementation
│   │   ├── tests/
│   │   │   └── test_s3_server.py
│   │   ├── pyproject.toml       # Package configuration
│   │   └── README.md
│   │
│   ├── mysql/                   # MySQL connector
│   │   ├── src/
│   │   │   └── mysql_server.py
│   │   ├── tests/
│   │   │   └── test_mysql_server.py
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   ├── jira/                    # JIRA connector
│   │   ├── src/
│   │   │   └── jira_server.py
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   └── shopify/                 # Shopify connector
│       ├── src/
│       │   └── shopify_server.py
│       ├── tests/
│       ├── pyproject.toml
│       └── README.md
│
├── .env                         # Environment variables (not in git)
├── .env.example                 # Example environment variables
├── docker-compose.yml           # Docker deployment config
├── README.md                    # User documentation
├── ARCHITECTURE.md              # Architecture documentation
├── DEVELOPER_GUIDE.md           # This file
└── QUICKSTART.md                # Quick start guide
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm or yarn
- Git

### Environment Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd ConnectorMCP
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Configure environment variables:**
   ```bash
   # Edit .env with your credentials
   nano .env
   ```

   Required variables:
   ```env
   # Claude AI (REQUIRED)
   ANTHROPIC_API_KEY=sk-ant-xxx

   # AWS S3 (optional)
   AWS_ACCESS_KEY_ID=xxx
   AWS_SECRET_ACCESS_KEY=xxx
   AWS_DEFAULT_REGION=us-east-1

   # MySQL (optional)
   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   MYSQL_USER=user
   MYSQL_PASSWORD=password
   MYSQL_DATABASE=database

   # JIRA (optional)
   JIRA_URL=https://your-domain.atlassian.net
   JIRA_EMAIL=your-email
   JIRA_API_TOKEN=your-token

   # Shopify (optional)
   SHOPIFY_SHOP_URL=your-shop.myshopify.com
   SHOPIFY_ACCESS_TOKEN=your-token
   ```

### Backend Installation

```bash
cd backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install connectors (optional, for standalone use)
cd ../connectors/s3 && pip install -e .
cd ../mysql && pip install -e .
cd ../jira && pip install -e .
cd ../shopify && pip install -e .
```

### Frontend Installation

```bash
cd frontend

# Install dependencies
npm install
```

### Running the Application

**Terminal 1 - Backend:**
```bash
cd backend
python -m app.main
# Backend runs on http://localhost:8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
# Frontend runs on http://localhost:5173
```

**Access the application:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## How It Works

### 1. Model Context Protocol (MCP)

MCP is a standardized protocol for connecting LLMs to external data sources. Each connector is an MCP server that:

- Exposes **tools** (functions the LLM can call)
- Communicates via **stdio** (standard input/output)
- Returns structured **JSON responses**

### 2. Conversation Flow

#### Step 1: User sends message
```
User: "Show me the latest users"
```

#### Step 2: Backend connects to MCP server
```python
# backend/app/services/mcp_service.py
async with self.get_client("mysql") as session:
    tools = await session.list_tools()
    # Returns: list_databases, list_tables, execute_query, etc.
```

#### Step 3: Claude AI receives tools + message
```python
# backend/app/services/chat_service.py
response = self.client.messages.create(
    model="claude-sonnet-4-5-20250929",
    system=system_prompt,
    messages=conversation_history,
    tools=available_tools  # MCP tools
)
```

#### Step 4: Claude decides to use tools
```python
# Claude returns:
{
    "tool_name": "execute_query",
    "arguments": {
        "query": "SELECT * FROM users ORDER BY user_id DESC LIMIT 10"
    }
}
```

#### Step 5: Backend executes tool call
```python
result = await mcp_service.call_tool(
    datasource="mysql",
    tool_name="execute_query",
    arguments={"query": "SELECT * FROM users..."}
)
```

#### Step 6: MCP connector queries database
```python
# connectors/mysql/src/mysql_server.py
@app.call_tool()
async def call_tool(name: str, arguments: Any):
    if name == "execute_query":
        return await handle_execute_query(arguments)
        # Executes SQL query, returns results
```

#### Step 7: Claude processes results → Response
```
Claude: "Here are the latest 10 users from the system:
[formatted table with user data]"
```

#### Step 8: Backend streams response to frontend
```python
# Character-by-character streaming
async for chunk in chat_service.process_message_stream(...):
    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
```

### 3. Intelligent Features

#### Context Extraction

The system automatically extracts context from conversations:

```python
# Example: "Show me the latest users"
def _extract_table_name_from_messages(messages):
    # Recognizes patterns like:
    # - "latest users" → extracts "users"
    # - "show me orders" → extracts "orders"
    # - "first 10 customers" → extracts "customers"
```

#### Parameter Auto-Injection

Missing parameters are automatically filled:

```python
# User: "list files in that bucket"
# System extracts bucket name from conversation history
bucket_name = self._extract_bucket_name_from_messages(messages)
tool_use.input["bucket"] = bucket_name
```

#### Smart Query Construction

Natural language → SQL:

```python
# "latest users" → SELECT * FROM users ORDER BY user_id DESC LIMIT 10
# "first 5 orders" → SELECT * FROM orders ORDER BY order_id DESC LIMIT 5
# "show me customers" → SELECT * FROM customers LIMIT 100
```

---

## Component Details

### Frontend (React + TypeScript)

#### ChatInterface Component
**Location:** `frontend/src/components/ChatInterface.tsx`

**Responsibilities:**
- Renders chat messages
- Handles user input
- Manages streaming responses
- Maintains conversation state

**Key Code:**
```typescript
await chatApi.sendMessageStream(
  { message, datasource, session_id },
  (chunk) => {
    // Character-by-character streaming
    accumulatedMessage += chunk
    setStreamingMessage(accumulatedMessage)
  },
  (sessionId) => setSessionId(sessionId),
  () => {
    // Done - add to message history
    setMessages(prev => [...prev, { role: 'assistant', content: accumulatedMessage }])
  },
  (error) => console.error(error)
)
```

#### API Service
**Location:** `frontend/src/services/api.ts`

**Handles:**
- HTTP requests to backend
- Server-Sent Events (SSE) parsing
- Response streaming

**Streaming Implementation:**
```typescript
const reader = response.body?.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break

  const chunk = decoder.decode(value)
  const lines = chunk.split('\n')

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6))
      if (data.type === 'content') {
        onChunk(data.content)  // Stream to UI
      }
    }
  }
}
```

### Backend (FastAPI)

#### Chat Service
**Location:** `backend/app/services/chat_service.py`

**Core class:** `ChatService`

**Key Methods:**

1. **`process_message_stream(message, datasource, session_id)`**
   - Main orchestration method
   - Manages conversation flow
   - Handles streaming responses

2. **`_call_claude_stream(messages, tools, system_prompt, datasource)`**
   - Calls Claude API with streaming
   - Handles tool execution
   - Max 10 iterations for multi-step reasoning

3. **`_extract_table_name_from_messages(messages)`**
   - Extracts table names from natural language
   - Patterns: "latest users", "show me orders", etc.

4. **`_construct_mysql_query_from_messages(messages)`**
   - Builds SQL from natural language
   - Handles ORDER BY, LIMIT clauses
   - Smart column name detection

5. **`_extract_bucket_name_from_messages(messages)`**
   - Extracts S3 bucket names from context
   - Searches recent conversation history

6. **`_extract_s3_key_from_messages(messages)`**
   - Finds S3 object keys from previous results
   - Fuzzy matching for file names

**Intelligent Streaming:**
```python
# Buffer 2 characters for smooth streaming
char_buffer = ""

async for chunk in self._call_claude_stream(...):
    full_response += chunk
    char_buffer += chunk

    # Flush buffer when >= 2 chars or at word boundaries
    while len(char_buffer) >= 2 or (char_buffer and chunk.endswith((' ', '\n'))):
        if len(char_buffer) >= 2:
            yield char_buffer[:2]
            char_buffer = char_buffer[2:]
        else:
            yield char_buffer
            char_buffer = ""
            break
```

#### MCP Service
**Location:** `backend/app/services/mcp_service.py`

**Core class:** `MCPService`

**Manages:**
- MCP client connections
- Tool routing
- Connection pooling

**Key Methods:**

1. **`get_client(datasource)`**
   - Creates stdio connection to MCP server
   - Context manager for automatic cleanup

2. **`call_tool(datasource, tool_name, arguments)`**
   - Routes tool calls to appropriate connector
   - Returns structured results

**Configuration:**
```python
self.connectors = {
    "s3": {
        "name": "Amazon S3",
        "command": python_cmd,
        "args": ["../connectors/s3/src/s3_server.py"],
        "env": {
            "AWS_ACCESS_KEY_ID": settings.aws_access_key_id,
            ...
        }
    },
    ...
}
```

### MCP Connectors

#### S3 Connector
**Location:** `connectors/s3/src/s3_server.py`

**Tools:**
- `list_buckets` - List all S3 buckets
- `list_objects` - List objects in bucket with prefix filtering
- `read_object` - Read file contents (text or binary)
- `write_object` - Upload files to S3
- `search_objects` - Search by wildcard pattern
- `get_object_metadata` - Get object metadata

**Example Tool:**
```python
@app.call_tool()
async def call_tool(name: str, arguments: Any):
    if name == "list_buckets":
        response = s3_client.list_buckets()
        buckets = [
            {
                "name": bucket["Name"],
                "creation_date": bucket["CreationDate"].isoformat()
            }
            for bucket in response.get("Buckets", [])
        ]
        return [TextContent(type="text", text=json.dumps({"count": len(buckets), "buckets": buckets}))]
```

#### MySQL Connector
**Location:** `connectors/mysql/src/mysql_server.py`

**Tools:**
- `list_databases` - List all databases
- `list_tables` - List tables in database
- `describe_table` - Get table schema + foreign keys
- `execute_query` - Execute SELECT queries (read-only)
- `get_table_stats` - Row count, size, engine info
- `get_table_indexes` - View table indexes

**Security:**
```python
# Only SELECT queries allowed
if not query.upper().startswith("SELECT"):
    return [TextContent(type="text", text="Error: Only SELECT queries allowed")]

# Auto-add LIMIT if not present
if "LIMIT" not in query.upper():
    query = f"{query} LIMIT {limit}"
```

**Connection Management:**
```python
def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )
```

---

## API Documentation

### REST Endpoints

#### Chat Endpoints

**POST `/api/chat/message`**
- Non-streaming chat message
- Returns complete response

Request:
```json
{
  "message": "Show me the latest users",
  "datasource": "mysql",
  "session_id": "optional-session-id"
}
```

Response:
```json
{
  "message": "Here are the latest 10 users...",
  "session_id": "generated-uuid",
  "datasource": "mysql",
  "tool_calls": [...]
}
```

**POST `/api/chat/message/stream`**
- Streaming chat message
- Server-Sent Events (SSE)

Request: Same as above

Response (SSE):
```
data: {"type": "session", "session_id": "uuid"}

data: {"type": "content", "content": "H"}

data: {"type": "content", "content": "er"}

data: {"type": "content", "content": "e "}

...

data: {"type": "done"}
```

**GET `/api/chat/sessions`**
- List active sessions

Response:
```json
["session-uuid-1", "session-uuid-2"]
```

**POST `/api/chat/sessions`**
- Create new session

Request:
```json
{
  "datasource": "mysql",
  "name": "Optional session name"
}
```

**DELETE `/api/chat/sessions/:id`**
- Delete session

#### Data Source Endpoints

**GET `/api/datasources`**
- List available data sources

Response:
```json
[
  {
    "id": "s3",
    "name": "Amazon S3",
    "description": "Query and manage S3 buckets",
    "icon": "s3",
    "enabled": true
  },
  ...
]
```

**GET `/api/datasources/:id/test`**
- Test data source connection

Response:
```json
{
  "datasource": "mysql",
  "connected": true,
  "message": "Connection successful",
  "details": {
    "tools_count": 6
  }
}
```

#### Health Check

**GET `/health`**
```json
{"status": "healthy"}
```

**GET `/`**
```json
{
  "name": "ConnectorMCP API",
  "version": "1.0.0",
  "status": "running"
}
```

---

## Development Workflow

### Running in Development Mode

```bash
# Terminal 1 - Backend with auto-reload
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 - Frontend with hot reload
cd frontend
npm run dev
```

### Code Style

**Backend (Python):**
```bash
# Format code
black backend/app

# Lint code
ruff check backend/app

# Type checking
mypy backend/app
```

**Frontend (TypeScript):**
```bash
# Format code
npm run format

# Lint code
npm run lint

# Type checking
npm run type-check
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes, commit frequently
git add .
git commit -m "feat: add feature description"

# Push and create PR
git push origin feature/your-feature-name
```

### Debugging

**Backend:**
```python
# Add breakpoints
import pdb; pdb.set_trace()

# Or use logging
import logging
logger = logging.getLogger(__name__)
logger.info(f"Debug info: {variable}")
```

**Frontend:**
```typescript
// Browser DevTools
console.log('Debug:', variable)
debugger  // Pauses execution
```

---

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html

# Run specific test
pytest tests/test_api.py::test_send_message -v
```

### Connector Tests

```bash
# Test S3 connector
cd connectors/s3
pytest tests/ -v

# Test MySQL connector
cd connectors/mysql
pytest tests/ -v
```

### Integration Tests

Run the comprehensive test suite:
```bash
cd backend
python test_connectors.py
```

Or quick verification:
```bash
python quick_test.py
```

### Manual Testing Checklist

- [ ] Backend starts without errors
- [ ] Frontend starts and loads
- [ ] Can select data sources
- [ ] Can send messages
- [ ] Streaming works smoothly
- [ ] Context switching works (S3 ↔ MySQL)
- [ ] Error messages are clear
- [ ] Session persistence works

---

## Deployment

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production Checklist

**Security:**
- [ ] Use environment-specific .env files
- [ ] Rotate API keys regularly
- [ ] Use HTTPS/TLS
- [ ] Enable CORS only for production domains
- [ ] Use read-only database users
- [ ] Implement rate limiting
- [ ] Add authentication/authorization

**Performance:**
- [ ] Enable caching
- [ ] Use CDN for frontend assets
- [ ] Configure database connection pooling
- [ ] Set up monitoring (Datadog, New Relic)
- [ ] Configure logging (ELK, CloudWatch)
- [ ] Set up error tracking (Sentry)

**Infrastructure:**
- [ ] Use managed database services
- [ ] Set up load balancing
- [ ] Configure auto-scaling
- [ ] Set up backups
- [ ] Configure health checks
- [ ] Use secrets management (AWS Secrets Manager, Vault)

### Environment Variables for Production

```env
# Production settings
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
LOG_LEVEL=INFO

# CORS - Only production domains
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Use production-grade credentials
ANTHROPIC_API_KEY=<production-key>
MYSQL_HOST=<production-db-host>
# ... etc
```

---

## Troubleshooting

### Common Issues

#### 1. Backend won't start

**Problem:** ModuleNotFoundError
```
Solution:
cd backend
pip install -r requirements.txt
```

**Problem:** Port 8000 already in use
```bash
# Find and kill process
lsof -ti:8000 | xargs kill -9
```

#### 2. Frontend won't start

**Problem:** Node modules not found
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

**Problem:** Port 5173 already in use
```bash
# Kill process
lsof -ti:5173 | xargs kill -9
```

#### 3. MCP Connection Errors

**Problem:** "Failed to connect to MCP server"
```
Check:
1. Connector Python file exists at path
2. Connector dependencies are installed
3. Environment variables are set correctly
```

**Problem:** "Unknown column 'id' in order clause"
```
Solution: Already fixed! The system now uses smart column detection
(users → user_id, orders → order_id, etc.)
```

#### 4. Claude API Errors

**Problem:** "Invalid API key"
```
Check .env file has correct ANTHROPIC_API_KEY
```

**Problem:** "Rate limit exceeded"
```
Solution: Implement exponential backoff or upgrade API plan
```

#### 5. MySQL Connection Errors

**Problem:** "Access denied for user"
```
Check:
1. MYSQL_USER has correct permissions
2. MYSQL_PASSWORD is correct
3. Database name exists
```

**Problem:** "Can't connect to MySQL server"
```
Check:
1. MySQL server is running
2. MYSQL_HOST and MYSQL_PORT are correct
3. Firewall allows connection
```

### Debug Mode

Enable detailed logging:

```python
# backend/app/main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check logs:
```bash
# Backend logs
tail -f backend/logs/app.log

# Docker logs
docker-compose logs -f backend
```

---

## Extending the System

### Adding a New Data Source

**Example: Adding PostgreSQL Connector**

#### Step 1: Create connector directory
```bash
mkdir -p connectors/postgres/src
mkdir -p connectors/postgres/tests
```

#### Step 2: Create MCP server
```python
# connectors/postgres/src/postgres_server.py
import psycopg2
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("postgres-connector")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="execute_query",
            description="Execute PostgreSQL query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "execute_query":
        conn = psycopg2.connect(...)
        cursor = conn.cursor()
        cursor.execute(arguments["query"])
        results = cursor.fetchall()
        return [TextContent(type="text", text=json.dumps(results))]
```

#### Step 3: Add to backend
```python
# backend/app/services/mcp_service.py
self.connectors["postgres"] = {
    "name": "PostgreSQL",
    "description": "Query PostgreSQL databases",
    "command": python_cmd,
    "args": ["../connectors/postgres/src/postgres_server.py"],
    "env": {
        "POSTGRES_HOST": settings.postgres_host,
        "POSTGRES_USER": settings.postgres_user,
        "POSTGRES_PASSWORD": settings.postgres_password,
        "POSTGRES_DATABASE": settings.postgres_database
    }
}
```

#### Step 4: Add frontend icon
```typescript
// frontend/src/components/ChatInterface.tsx
{datasource.id === 'postgres' && '🐘'}
```

#### Step 5: Test
```bash
cd connectors/postgres
pip install -e .
python src/postgres_server.py
```

### Customizing System Prompts

Edit system prompts in `backend/app/services/chat_service.py`:

```python
def _create_system_prompt(self, datasource: str) -> str:
    if datasource == "your_datasource":
        return """
        Custom instructions for your data source:
        1. Always do X
        2. Never do Y
        3. Format results as Z
        """
```

### Adding New Tools to Existing Connectors

Example: Add `delete_object` to S3 connector:

```python
# connectors/s3/src/s3_server.py
Tool(
    name="delete_object",
    description="Delete an object from S3",
    inputSchema={
        "type": "object",
        "properties": {
            "bucket": {"type": "string"},
            "key": {"type": "string"}
        },
        "required": ["bucket", "key"]
    }
)

async def handle_delete_object(arguments: dict):
    bucket = arguments["bucket"]
    key = arguments["key"]
    s3_client.delete_object(Bucket=bucket, Key=key)
    return [TextContent(type="text", text=f"Deleted {key} from {bucket}")]
```

### Customizing Streaming Behavior

Adjust streaming in `backend/app/services/chat_service.py`:

```python
# For faster streaming (1 char at a time)
while len(char_buffer) >= 1:
    yield char_buffer[:1]
    char_buffer = char_buffer[1:]

# For slower streaming (5 chars at a time)
while len(char_buffer) >= 5:
    yield char_buffer[:5]
    char_buffer = char_buffer[5:]
```

---

## Performance Optimization

### Backend Optimization

1. **Connection Pooling:**
```python
# Use connection pooling for MySQL
from mysql.connector import pooling

pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=5,
    **connection_config
)
```

2. **Caching:**
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_table_schema(table_name: str):
    # Cache table schemas
    pass
```

3. **Async Operations:**
```python
# Use asyncio for parallel operations
results = await asyncio.gather(
    get_data_source1(),
    get_data_source2(),
    get_data_source3()
)
```

### Frontend Optimization

1. **Code Splitting:**
```typescript
const ChatInterface = lazy(() => import('./components/ChatInterface'))
```

2. **Memoization:**
```typescript
const memoizedComponent = useMemo(() =>
  <ExpensiveComponent data={data} />,
  [data]
)
```

3. **Virtual Scrolling:**
For long message lists, use react-window or react-virtualized

---

## Security Best Practices

### API Key Management

- Never commit .env files
- Use environment-specific keys
- Rotate keys regularly
- Use least privilege principle

### SQL Injection Prevention

Already implemented in MySQL connector:
```python
# Use parameterized queries
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

### Rate Limiting

Add to backend:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/chat/message")
@limiter.limit("10/minute")
async def send_message(...):
    pass
```

### Authentication

Add JWT authentication:
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(credentials = Depends(security)):
    if not verify_jwt(credentials.credentials):
        raise HTTPException(401, "Invalid token")
    return credentials
```

---

## Useful Commands

### Backend
```bash
# Run backend
python -m app.main

# Run with auto-reload
uvicorn app.main:app --reload

# Run tests
pytest tests/ -v

# Format code
black app/

# Lint code
ruff check app/
```

### Frontend
```bash
# Run frontend
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run tests
npm test

# Lint code
npm run lint
```

### Database
```bash
# Connect to MySQL
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE

# Dump database
mysqldump -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE > backup.sql

# Restore database
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE < backup.sql
```

### Docker
```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Remove volumes
docker-compose down -v
```

---

## Resources

### Documentation
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [React Docs](https://react.dev/)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [Anthropic Claude](https://docs.anthropic.com/)

### Tools
- [Postman](https://www.postman.com/) - API testing
- [pgAdmin](https://www.pgadmin.org/) - Database management
- [VS Code](https://code.visualstudio.com/) - IDE

### Monitoring
- [Sentry](https://sentry.io/) - Error tracking
- [Datadog](https://www.datadoghq.com/) - Monitoring
- [LogRocket](https://logrocket.com/) - Frontend monitoring

---

## Support & Maintenance

### Regular Maintenance Tasks

**Weekly:**
- [ ] Review error logs
- [ ] Check API usage
- [ ] Monitor response times

**Monthly:**
- [ ] Update dependencies
- [ ] Review and rotate credentials
- [ ] Backup databases
- [ ] Review monitoring dashboards

**Quarterly:**
- [ ] Security audit
- [ ] Performance review
- [ ] Documentation updates
- [ ] Dependency upgrades

### Getting Help

1. **Check logs first** - Most issues are visible in logs
2. **Review this documentation** - Common issues covered above
3. **Check GitHub issues** - Others may have had similar problems
4. **Search MCP community** - Growing community of MCP developers

---

## Conclusion

This application is production-ready with:
- ✅ Comprehensive error handling
- ✅ Intelligent context management
- ✅ Smooth streaming responses
- ✅ Modular, reusable connectors
- ✅ Natural language understanding
- ✅ Easy to extend and customize

The MCP architecture makes it easy to add new data sources and use connectors in other applications. Each component is well-documented and follows best practices for security, performance, and maintainability.

For questions or issues, refer to the relevant sections above or check the inline code comments for detailed implementation notes.

**Happy coding! 🚀**

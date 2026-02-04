# ConnectorMCP Developer Handoff Document

**Last Updated:** January 2026
**Current Branch:** `santosh-oauth`
**Main Branch:** `main`

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Quick Start](#2-quick-start)
3. [Architecture Overview](#3-architecture-overview)
4. [Project Structure](#4-project-structure)
5. [Backend Deep Dive](#5-backend-deep-dive)
6. [Frontend Deep Dive](#6-frontend-deep-dive)
7. [MCP Connectors](#7-mcp-connectors)
8. [Database Schema](#8-database-schema)
9. [Authentication System](#9-authentication-system)
10. [Configuration Reference](#10-configuration-reference)
11. [API Reference](#11-api-reference)
12. [Development Workflows](#12-development-workflows)
13. [Testing](#13-testing)
14. [Deployment](#14-deployment)
15. [Production Hardening Features](#15-production-hardening-features)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Project Overview

### What is ConnectorMCP?

ConnectorMCP (also known as "Mosaic") is an AI-powered data aggregation platform that enables users to query multiple enterprise data sources using natural language. Instead of logging into Slack, JIRA, databases, and other tools separately, users can ask a single question and get a unified answer from all relevant sources.

### Core Capabilities

- **Natural Language Queries:** "What did Sarah say about the budget?" → searches Slack, email, documents
- **Multi-Source Aggregation:** Query 7+ data sources simultaneously
- **Real-Time Streaming:** See AI thinking and tool execution in real-time
- **Multi-Tenant Support:** Organizations can connect shared datasources for all members
- **Secure Credential Storage:** Encrypted at rest with key rotation support

### Supported Data Sources

| Source | Description | Auth Type |
|--------|-------------|-----------|
| Slack | Messages, channels, DMs | OAuth (Bot + User tokens) |
| GitHub | Repos, PRs, issues, code search | OAuth / PAT |
| JIRA | Issues, projects, sprints | OAuth / API token |
| Google Workspace | Drive, Docs, Sheets, Calendar, Gmail | OAuth 2.0 |
| AWS S3 | Buckets, objects, content | Access keys |
| MySQL | Tables, queries, schema | Connection string |
| Shopify | Products, orders, customers | API token |

### Tech Stack

**Backend:**
- Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic v2
- Anthropic Claude (claude-3-5-sonnet) for AI
- MCP (Model Context Protocol) for connector communication

**Frontend:**
- React 18, TypeScript 5.3, Vite
- TailwindCSS, React Query v5, React Router v7

**Infrastructure:**
- MySQL (primary database)
- Redis (optional, for distributed rate limiting)
- Docker, Docker Compose

---

## 2. Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Anthropic API key

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings (see Configuration section)

# Start the backend
python -m app.main
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Verify Installation

1. Backend health: http://localhost:8000/health
2. Frontend: http://localhost:5173
3. API docs: http://localhost:8000/docs

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend (React)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐│
│  │  Auth    │  │  Chat    │  │ Settings │  │ What You Missed      ││
│  │ Context  │  │Interface │  │  Panel   │  │    Dashboard         ││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘│
└───────┼─────────────┼─────────────┼────────────────────┼────────────┘
        │             │             │                    │
        └─────────────┴─────────────┴────────────────────┘
                              │ HTTPS/WSS
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                      API Layer                                │  │
│  │  /api/auth  /api/chat  /api/credentials  /api/agent  /api/admin│ │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                             │                                       │
│  ┌──────────────────────────┴───────────────────────────────────┐  │
│  │                    Service Layer                              │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐              │  │
│  │  │ ChatService│  │MCPService  │  │AgentService│              │  │
│  │  │ (Claude)   │  │(Connectors)│  │(Multi-src) │              │  │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘              │  │
│  │        │               │               │                      │  │
│  │  ┌─────┴───────────────┴───────────────┴──────┐              │  │
│  │  │  CredentialService  │  AuthService         │              │  │
│  │  │  (Encryption)       │  (JWT/OAuth)         │              │  │
│  │  └────────────────────────────────────────────┘              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│    MySQL      │    │ MCP Connectors│    │  External APIs│
│  (App State)  │    │ (stdio pipes) │    │ (Slack, etc.) │
└───────────────┘    └───────────────┘    └───────────────┘
```

### Request Flow Example

1. User types: "What PRs need my review?"
2. Frontend sends POST to `/api/chat/message/stream`
3. ChatService receives message, determines datasource (GitHub)
4. MCPService retrieves user's GitHub credentials (encrypted)
5. MCPService spawns GitHub MCP connector subprocess
6. Connector authenticates with GitHub API
7. Claude analyzes available tools, selects `get_pull_requests`
8. Tool results returned to Claude for summarization
9. Response streamed back to frontend with agent steps

---

## 4. Project Structure

```
ConnectorMCP/
├── backend/
│   ├── app/
│   │   ├── api/                    # Route handlers
│   │   │   ├── auth.py            # Authentication endpoints
│   │   │   ├── chat.py            # Chat message endpoints
│   │   │   ├── credentials.py     # Credential management
│   │   │   ├── admin.py           # Admin/tenant management
│   │   │   ├── agent.py           # Multi-source queries
│   │   │   ├── datasources.py     # Datasource listing
│   │   │   ├── digest.py          # "What You Missed"
│   │   │   └── health.py          # Health checks
│   │   │
│   │   ├── services/               # Business logic
│   │   │   ├── mcp_service.py     # MCP client management (★ CORE)
│   │   │   ├── chat_service.py    # Message processing (★ CORE)
│   │   │   ├── agent_service.py   # Multi-source orchestration
│   │   │   ├── credential_service.py # Encryption/storage
│   │   │   ├── auth_service.py    # JWT/user management
│   │   │   ├── oauth_state_service.py # OAuth CSRF protection
│   │   │   ├── tenant_service.py  # Multi-tenant support
│   │   │   └── ...
│   │   │
│   │   ├── models/
│   │   │   ├── database.py        # SQLAlchemy ORM models
│   │   │   ├── chat.py            # Chat request/response schemas
│   │   │   └── ...
│   │   │
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic settings
│   │   │   ├── database.py        # DB session management
│   │   │   ├── security.py        # Token generation
│   │   │   ├── telemetry.py       # OpenTelemetry
│   │   │   ├── metrics.py         # Performance metrics
│   │   │   └── logging.py         # Structured logging
│   │   │
│   │   ├── middleware/
│   │   │   ├── auth.py            # JWT validation
│   │   │   └── rate_limit.py      # Rate limiting
│   │   │
│   │   ├── connectors/             # Connector configurations
│   │   │   ├── base.py            # BaseConnector class
│   │   │   ├── slack.py
│   │   │   ├── github.py
│   │   │   └── ...
│   │   │
│   │   └── main.py                 # FastAPI app entry point
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── components/             # React components
│   │   │   ├── ChatInterface.tsx  # Main chat UI
│   │   │   ├── MessageList.tsx
│   │   │   ├── SettingsPanel.tsx  # OAuth/credentials
│   │   │   └── ...
│   │   │
│   │   ├── contexts/
│   │   │   ├── AuthContext.tsx    # Authentication state
│   │   │   └── ThemeContext.tsx   # Dark/light mode
│   │   │
│   │   ├── pages/
│   │   │   └── LoginPage.tsx
│   │   │
│   │   ├── services/
│   │   │   └── api.ts             # Axios API client
│   │   │
│   │   ├── types/
│   │   │   └── index.ts           # TypeScript interfaces
│   │   │
│   │   ├── App.tsx                # Root component
│   │   └── main.tsx               # Entry point
│   │
│   ├── package.json
│   └── vite.config.ts
│
├── connectors/                     # MCP connector servers
│   ├── slack/
│   │   ├── src/slack_server.py
│   │   └── README.md
│   ├── github/
│   ├── jira/
│   ├── google_workspace/          # Complex (34 files)
│   ├── s3/
│   ├── shopify/
│   └── mysql/
│
├── docs/
│   ├── DEPLOYMENT.md
│   ├── RUNBOOK.md
│   ├── INCIDENT_RESPONSE.md
│   ├── SECURITY_CHECKLIST.md
│   └── Technical_Architecture.md
│
├── docker-compose.yml
├── Jenkinsfile
├── README.md
└── .env.example
```

---

## 5. Backend Deep Dive

### Key Services

#### MCPService (`services/mcp_service.py`) - 36KB

The heart of connector communication. Manages MCP client lifecycle.

**Responsibilities:**
- Spawns MCP connector subprocesses via stdio
- Manages connection pooling (5-min idle timeout)
- Caches tools, results, and schemas
- Handles token refresh for OAuth connectors
- Implements circuit breaker for reliability

**Key Methods:**
```python
# Get available datasources
await mcp_service.get_available_datasources()

# List tools for a datasource
tools = await mcp_service.list_tools("slack", user_id=user.id)

# Execute a tool
result = await mcp_service.call_tool(
    datasource="slack",
    tool_name="search_messages",
    arguments={"query": "budget meeting"},
    user_id=user.id,
    db=db
)
```

**Caching Strategy:**
- Tools Cache: 5 minutes TTL
- Result Cache: 30 seconds TTL
- Schema Cache: 10 minutes TTL (MySQL)

#### ChatService (`services/chat_service.py`) - 40KB

Orchestrates message processing with Claude.

**Flow:**
1. Receive user message
2. Load conversation history from database
3. Get available tools for selected datasource
4. Send to Claude with system prompt
5. Execute any tool calls Claude requests
6. Return formatted response

**Key Methods:**
```python
# Process single message (blocking)
response, tool_calls = await chat_service.process_message(
    message="What are my open issues?",
    datasource="jira",
    session_id="abc123",
    user_id=user.id,
    db=db
)

# Process with streaming (SSE)
async for chunk in chat_service.process_message_stream(...):
    yield chunk
```

#### CredentialService (`services/credential_service.py`) - 19KB

Manages encrypted credential storage with key rotation.

**Security Features:**
- Fernet symmetric encryption (AES-128)
- Versioned format: `v2:<ciphertext>`
- Automatic migration from legacy formats
- Per-user encrypted storage

**Key Methods:**
```python
# Save credentials (auto-encrypts)
await credential_service.save_credentials(
    datasource="github",
    credentials={"access_token": "ghp_xxx"},
    user_id=user.id,
    db=db
)

# Retrieve credentials (auto-decrypts)
creds = await credential_service.get_credentials(
    datasource="github",
    user_id=user.id,
    db=db
)
```

### Middleware

#### Authentication (`middleware/auth.py`)

```python
from app.middleware.auth import get_current_user, get_current_user_optional

# Require authentication
@router.get("/protected")
async def protected_endpoint(user: User = Depends(get_current_user)):
    return {"user_id": user.id}

# Optional authentication (works for anonymous)
@router.get("/public")
async def public_endpoint(user: Optional[User] = Depends(get_current_user_optional)):
    if user:
        return {"authenticated": True}
    return {"authenticated": False}
```

#### Rate Limiting (`middleware/rate_limit.py`)

- Sliding window algorithm
- Per-IP tracking with X-Forwarded-For support
- Configurable minute/hour limits
- Redis backend available for distributed deployments

---

## 6. Frontend Deep Dive

### Component Architecture

```
App.tsx
├── AuthProvider (context)
│   └── ThemeProvider (context)
│       └── BrowserRouter
│           ├── /login → LoginPage
│           └── /* → ProtectedRoute
│               └── MainLayout
│                   ├── DataSourceSidebar
│                   ├── ChatInterface
│                   │   ├── ChatHeader
│                   │   ├── MessageList
│                   │   │   └── MarkdownMessage
│                   │   ├── ThinkingIndicator
│                   │   └── MessageInput
│                   ├── SettingsPanel
│                   └── WhatYouMissedDashboard
```

### State Management

**AuthContext** - User authentication state
```typescript
const { user, isLoading, login, logout, isAuthenticated } = useAuth();
```

**ThemeContext** - Dark/light mode
```typescript
const { isDark, toggleTheme } = useTheme();
```

**React Query** - Server state caching
```typescript
// Cached user data with automatic refetch
const { data: user } = useQuery({
  queryKey: ['user'],
  queryFn: fetchCurrentUser,
  staleTime: 5 * 60 * 1000, // 5 minutes
});
```

### Key Components

**ChatInterface.tsx** - Main chat container
- Handles message sending (streaming)
- Displays agent activity steps
- Manages scroll position

**SettingsPanel.tsx** - Credential/OAuth management
- Lists connected datasources
- OAuth flow initiation
- Manual credential entry

**MessageList.tsx** - Message display
- Markdown rendering
- Code syntax highlighting
- Source citations

### API Client (`services/api.ts`)

```typescript
import api from './api';

// Chat message
const response = await api.post('/chat/message/stream', {
  message: "What's new in Slack?",
  datasource: "slack",
  session_id: sessionId
});

// Check credentials
const status = await api.get('/credentials/slack/status');
```

---

## 7. MCP Connectors

### How MCP Works

MCP (Model Context Protocol) is a standard for AI-tool communication. Each connector is a standalone Python server that:

1. Declares available tools (functions)
2. Receives tool calls from the backend
3. Executes calls against external APIs
4. Returns structured results

### Connector Structure

```python
# Example: connectors/slack/src/slack_server.py

from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("slack")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_messages",
            description="Search Slack messages",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "channel": {"type": "string"},
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "search_messages":
        results = await slack_api.search(arguments["query"])
        return [TextContent(type="text", text=json.dumps(results))]
```

### Adding a New Connector

1. **Create connector directory:**
   ```
   connectors/newservice/
   ├── src/newservice_server.py
   ├── requirements.txt
   ├── pyproject.toml
   └── README.md
   ```

2. **Register in backend:**
   ```python
   # backend/app/connectors/newservice.py
   from .base import BaseConnector

   class NewServiceConnector(BaseConnector):
       metadata = {
           "id": "newservice",
           "name": "New Service",
           "description": "Connect to New Service",
           "icon": "new-service-icon"
       }

       credential_fields = [
           {"name": "api_key", "label": "API Key", "type": "password"}
       ]

       def get_server_command(self, credentials: dict) -> list:
           return [
               "python", "-m", "newservice_server",
               "--api-key", credentials["api_key"]
           ]
   ```

3. **Update frontend icon** in `DataSourceIcon.tsx`

### Available Connectors

| Connector | Tools | Auth |
|-----------|-------|------|
| Slack | search_messages, list_channels, get_user_info | Bot + User tokens |
| GitHub | list_repos, search_code, get_issues, get_prs | OAuth / PAT |
| JIRA | search_issues, get_issue, list_projects | OAuth / API token |
| Google Workspace | 30+ tools across Drive, Docs, Sheets, Calendar | OAuth 2.0 |
| S3 | list_buckets, list_objects, get_content | Access keys |
| MySQL | query, list_tables, describe_table | Connection string |
| Shopify | list_products, list_orders, get_customer | API token |

---

## 8. Database Schema

### Entity Relationship

```
tenants
    │
    ├──< users (tenant_id FK)
    │       │
    │       ├──< user_credentials (user_id FK)
    │       │
    │       └──< chat_history (user_id FK)
    │
    └──< tenant_datasources (tenant_id FK)
             │
             └── connected_by → users.id

oauth_states (standalone - CSRF protection)

anonymous_sessions (standalone - legacy support)
```

### Tables

#### `users`
```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),          -- NULL for OAuth users
    name VARCHAR(255),
    profile_picture TEXT,
    tenant_id VARCHAR(36),               -- FK to tenants
    role VARCHAR(20) DEFAULT 'member',   -- 'admin' or 'member'
    auth_provider VARCHAR(20) DEFAULT 'email',
    google_id VARCHAR(255) UNIQUE,
    last_login DATETIME,
    previous_login DATETIME,             -- For "What You Missed"
    created_at DATETIME,
    updated_at DATETIME
);
```

#### `tenants`
```sql
CREATE TABLE tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) UNIQUE,          -- e.g., "kaaylabs.com"
    created_at DATETIME,
    updated_at DATETIME
);
```

#### `user_credentials`
```sql
CREATE TABLE user_credentials (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,        -- FK to users
    datasource VARCHAR(50) NOT NULL,     -- 'slack', 'github', etc.
    encrypted_credentials TEXT NOT NULL, -- v2:<ciphertext>
    created_at DATETIME,
    updated_at DATETIME,
    UNIQUE KEY (user_id, datasource)
);
```

#### `chat_history`
```sql
CREATE TABLE chat_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    datasource VARCHAR(50),
    role VARCHAR(20),                    -- 'user' or 'assistant'
    content TEXT,
    created_at DATETIME,
    INDEX (user_id, datasource, created_at),
    INDEX (user_id, session_id)
);
```

#### `oauth_states`
```sql
CREATE TABLE oauth_states (
    state VARCHAR(64) PRIMARY KEY,       -- Random token
    context JSON,                        -- {user_id, tenant_id, datasource}
    created_at DATETIME,
    expires_at DATETIME NOT NULL,        -- 10 minute TTL
    INDEX (expires_at)
);
```

---

## 9. Authentication System

### JWT Authentication

**Token Structure:**
```json
{
  "user_id": "uuid-here",
  "email": "user@example.com",
  "exp": 1705123456
}
```

**Token Storage:** HTTPOnly cookie named `access_token`
**Expiration:** 24 hours (configurable)
**Algorithm:** HS256

### Authentication Flows

#### Email/Password
```
1. POST /api/auth/signup {email, password, name}
   → Creates user, returns JWT in cookie

2. POST /api/auth/login {email, password}
   → Validates credentials, updates last_login, returns JWT

3. POST /api/auth/logout
   → Clears JWT cookie
```

#### Google OAuth
```
1. GET /api/auth/google
   → Generates state token, stores in DB
   → Redirects to Google consent screen

2. Google redirects to /api/auth/google/callback?code=xxx&state=yyy
   → Validates state (one-time use)
   → Exchanges code for Google tokens
   → Creates/updates user
   → Returns JWT in cookie
```

#### Per-User Datasource OAuth
```
1. GET /api/credentials/{datasource}/oauth
   → Generates state with user context
   → Redirects to provider (Slack/GitHub/JIRA)

2. Provider redirects to /api/credentials/{datasource}/oauth/callback
   → Validates state, exchanges code
   → Encrypts and stores tokens per-user
```

---

## 10. Configuration Reference

### Required Environment Variables

```bash
# Core (REQUIRED)
ANTHROPIC_API_KEY=sk-ant-xxx        # Claude API key
JWT_SECRET_KEY=your-64-char-secret  # Min 32 chars in production
ENCRYPTION_KEY=fernet-key-here      # Generate with Fernet.generate_key()

# Database (REQUIRED)
LOCAL_MYSQL_HOST=localhost
LOCAL_MYSQL_PORT=3306
LOCAL_MYSQL_USER=root
LOCAL_MYSQL_PASSWORD=password
LOCAL_MYSQL_DATABASE=connectorMCP

# Application
ENVIRONMENT=development             # development, staging, production
FRONTEND_URL=http://localhost:5173
API_BASE_URL=http://localhost:8000
```

### Optional Configuration

```bash
# Security
ENCRYPTION_KEY_V1=                  # Legacy key for rotation
COOKIE_SECURE=false                 # true in production (HTTPS)
COOKIE_SAMESITE=lax                 # strict in production

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_HOUR=1000
RATE_LIMIT_BACKEND=memory           # or 'redis'
TRUSTED_PROXIES=                    # IP list for X-Forwarded-For

# OAuth Providers
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=

SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_OAUTH_REDIRECT_URI=

GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_OAUTH_REDIRECT_URI=

# Observability
LOG_LEVEL=INFO                      # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=development              # or 'json' for structured
OTEL_EXPORTER_OTLP_ENDPOINT=        # OpenTelemetry endpoint

# Default Datasource Credentials (fallback)
SLACK_BOT_TOKEN=xoxb-xxx
GITHUB_TOKEN=ghp_xxx
JIRA_URL=https://company.atlassian.net
JIRA_EMAIL=user@company.com
JIRA_API_TOKEN=xxx
```

---

## 11. API Reference

### Chat Endpoints

```http
POST /api/chat/message/stream
Content-Type: application/json

{
  "message": "What PRs need my review?",
  "datasource": "github",
  "session_id": "optional-session-id"
}

Response: Server-Sent Events stream
data: {"type": "session", "session_id": "abc123"}
data: {"type": "agent_step", "step": {"id": "1", "type": "thinking", "status": "active"}}
data: {"type": "content", "content": "Looking at your PRs..."}
data: {"type": "done", "sources": [...], "follow_up_questions": [...]}
```

### Credentials Endpoints

```http
# Check if credentials configured
GET /api/credentials/github/status
→ {"configured": true}

# Save credentials manually
POST /api/credentials
{
  "datasource": "github",
  "credentials": {"access_token": "ghp_xxx"}
}

# Start OAuth flow
GET /api/credentials/github/oauth
→ Redirects to GitHub authorization
```

### Agent Endpoints (Multi-Source)

```http
POST /api/agent/query/stream
{
  "query": "What happened while I was away?",
  "sources": ["slack", "github", "jira"]  // optional, auto-detected if omitted
}
```

---

## 12. Development Workflows

### Adding a New API Endpoint

1. Create route in `backend/app/api/yourmodule.py`:
   ```python
   from fastapi import APIRouter, Depends
   from app.middleware.auth import get_current_user

   router = APIRouter(prefix="/api/yourmodule", tags=["YourModule"])

   @router.get("/items")
   async def list_items(user: User = Depends(get_current_user)):
       return {"items": []}
   ```

2. Register router in `main.py`:
   ```python
   from app.api import yourmodule
   app.include_router(yourmodule.router)
   ```

3. Add frontend API call in `services/api.ts`:
   ```typescript
   export const getItems = () => api.get('/yourmodule/items');
   ```

### Database Migrations

```bash
cd backend

# Create migration
alembic revision --autogenerate -m "Add new_column to users"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Key Rotation

1. Generate new encryption key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Set environment variables:
   ```bash
   ENCRYPTION_KEY_V1=<old-key>       # Keep for decryption
   ENCRYPTION_KEY=<new-key>          # New key for encryption
   ```

3. Restart backend - credentials auto-migrate on read

---

## 13. Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py

# Run with verbose output
pytest -v
```

### Frontend Tests

```bash
cd frontend

# Unit tests
npm test

# E2E tests (Playwright)
npm run test:e2e

# Type checking
npm run typecheck
```

### Manual Testing

```bash
# Health check
curl http://localhost:8000/health

# List routes
curl http://localhost:8000/debug/routes

# Test with authentication
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}' \
  -c cookies.txt

curl http://localhost:8000/api/auth/me -b cookies.txt
```

---

## 14. Deployment

### Docker Deployment

```bash
# Build and run all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Rebuild after changes
docker-compose up -d --build
```

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set strong `JWT_SECRET_KEY` (64+ chars)
- [ ] Set `ENCRYPTION_KEY` (keep secure backup)
- [ ] Set `COOKIE_SECURE=true` (requires HTTPS)
- [ ] Configure `TRUSTED_PROXIES` if behind load balancer
- [ ] Set up database backups
- [ ] Configure monitoring (OpenTelemetry)
- [ ] Review rate limits for expected traffic

### Environment-Specific Config

| Setting | Development | Production |
|---------|-------------|------------|
| `ENVIRONMENT` | development | production |
| `LOG_FORMAT` | development | json |
| `COOKIE_SECURE` | false | true |
| `COOKIE_SAMESITE` | lax | strict |
| `RATE_LIMIT_BACKEND` | memory | redis |

---

## 15. Production Hardening Features

Recent security and reliability improvements:

### Security

1. **JWT Validation** - Startup fails if secret not set in production
2. **OAuth State Storage** - Database-backed (not in-memory) for multi-instance
3. **Credential Encryption** - v2 format with key rotation support
4. **Rate Limiting** - Sliding window with Redis support
5. **Trusted Proxy Validation** - Only trust X-Forwarded-For from configured IPs

### Reliability

1. **MCP Timeouts** - 30-second timeout on tool calls
2. **Circuit Breaker** - Prevents cascade failures
3. **Proactive Token Refresh** - Refreshes OAuth tokens before expiry
4. **Connection Pooling** - 5-minute idle timeout

### Observability

1. **Structured Logging** - JSON format with request IDs
2. **OpenTelemetry** - Distributed tracing support
3. **Metrics** - Connection duration, credential ops, OAuth flows
4. **Request Tracing** - X-Request-ID propagation

---

## 16. Troubleshooting

### Common Issues

**"Invalid JWT" errors:**
- Check `JWT_SECRET_KEY` is consistent across restarts
- Verify token hasn't expired (24h default)
- Clear browser cookies and re-login

**"Credentials not found" for OAuth datasource:**
- Check user has completed OAuth flow
- Verify credentials are stored: `SELECT * FROM user_credentials WHERE user_id='xxx'`
- Check encryption key hasn't changed

**MCP connector not responding:**
- Check connector dependencies: `pip install -r connectors/xxx/requirements.txt`
- Verify credentials are correct
- Check connector logs in backend output
- Try restarting backend to reset connections

**OAuth callback fails with "invalid state":**
- State tokens expire after 10 minutes
- Don't have multiple OAuth windows open
- Check database connectivity for `oauth_states` table

### Debug Logging

```bash
# Enable verbose logging
LOG_LEVEL=DEBUG python -m app.main

# Check specific service
grep "mcp_service" /var/log/app.log
grep "credential_service" /var/log/app.log
```

### Database Queries

```sql
-- Check user credentials
SELECT user_id, datasource, LEFT(encrypted_credentials, 20)
FROM user_credentials;

-- Check OAuth states (should be empty or few recent)
SELECT * FROM oauth_states WHERE expires_at > NOW();

-- Check chat history
SELECT * FROM chat_history WHERE user_id='xxx' ORDER BY created_at DESC LIMIT 10;
```

---

## Quick Reference

### Key Files

| Purpose | File |
|---------|------|
| App entry point | `backend/app/main.py` |
| Configuration | `backend/app/core/config.py` |
| Database models | `backend/app/models/database.py` |
| MCP client management | `backend/app/services/mcp_service.py` |
| Chat processing | `backend/app/services/chat_service.py` |
| Credential encryption | `backend/app/services/credential_service.py` |
| Frontend entry | `frontend/src/App.tsx` |
| Auth state | `frontend/src/contexts/AuthContext.tsx` |

### Useful Commands

```bash
# Start backend
cd backend && python -m app.main

# Start frontend
cd frontend && npm run dev

# Run tests
cd backend && pytest
cd frontend && npm test

# Database shell
mysql -h localhost -u root -p connectorMCP

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

**Document Version:** 1.0
**Last Updated:** January 2026
**Contact:** See repository contributors for questions

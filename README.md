# Mosaic by Kaay - Multi-Source Data Connector with Natural Language Interface

A production-level application that enables natural language interaction with multiple data sources (Amazon S3, MySQL, JIRA, Shopify, Google Workspace) through the Model Context Protocol (MCP) and Anthropic Claude.

**Mosaic** brings together different data sources into one unified, beautiful interface - like pieces of a mosaic creating a complete picture.

## Features

- 🤖 **Natural Language Queries**: Chat with your data sources using plain English
- 🔌 **Multiple Data Sources**: Support for S3, MySQL, JIRA, Shopify, and Google Workspace
- 🎯 **MCP Integration**: Each connector is a standalone MCP server
- 🚀 **Production Ready**: Comprehensive tests, Docker support, and production architecture
- 📦 **Modular Design**: Each connector can be exported and used independently
- 💬 **Modern UI**: React + TypeScript frontend with Google Material Design aesthetic
- 🌓 **Dark/Light Mode**: Seamless theme switching with user preference persistence

## Architecture

The application consists of three main layers:

1. **Frontend**: React + TypeScript chat interface with Google Material Design
2. **Backend**: FastAPI service that orchestrates MCP clients and Claude AI
3. **MCP Connectors**: Independent Python-based MCP servers for each data source

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed architecture documentation.

## UI/UX Design

The frontend features a clean, modern interface inspired by Google Material Design:

- **Google Material Design**: Clean borders, subtle shadows, appropriate spacing
- **Dark/Light Mode**: Toggle between themes with smooth transitions
- **Theme Persistence**: User preferences saved in browser localStorage
- **Responsive Layout**: Optimized for desktop and tablet viewing
- **Real-time Streaming**: Live chat responses with typing indicators
- **Accessible**: Semantic HTML and ARIA labels throughout

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional, for containerized deployment)
- Anthropic API key
- Credentials for data sources you want to use (AWS, MySQL, JIRA, Shopify)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd ConnectorMCP
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` and add your credentials:

```bash
# Required
ANTHROPIC_API_KEY=your_anthropic_api_key

# Optional - Configure only the data sources you want to use
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret

MYSQL_HOST=localhost
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=your_database

JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your_email
JIRA_API_TOKEN=your_token

SHOPIFY_SHOP_URL=your-shop.myshopify.com
SHOPIFY_ACCESS_TOKEN=your_token

GOOGLE_OAUTH_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
USER_GOOGLE_EMAIL=your_email@gmail.com
```

> **Note**: For Google Workspace setup, see [GOOGLE_WORKSPACE_SETUP.md](./GOOGLE_WORKSPACE_SETUP.md) for detailed OAuth 2.0 configuration instructions.

### 3. Install Dependencies

#### Backend

```bash
cd backend
pip install -r requirements.txt
```

#### Frontend

```bash
cd frontend
npm install
```

#### MCP Connectors (optional, for standalone use)

```bash
# S3 Connector
cd connectors/s3
pip install -e .

# MySQL Connector
cd connectors/mysql
pip install -e .

# JIRA Connector
cd connectors/jira
pip install -e .

# Shopify Connector
cd connectors/shopify
pip install -e .

# Google Workspace Connector
cd connectors/google_workspace
pip install -e .
```

### 4. Run the Application

#### Option A: Manual Start

Terminal 1 - Backend:
```bash
cd backend
python -m app.main
```

Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

#### Option B: Docker Compose

```bash
docker-compose up
```

### 5. Access the Application

Open your browser and navigate to:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## Usage

1. **Select a Data Source**: Click on a data source in the sidebar (S3, MySQL, JIRA, or Shopify)

2. **Start Chatting**: Type natural language queries in the chat interface

### Example Queries

#### S3
- "List all buckets"
- "Show me files in the 'data' bucket"
- "Read the contents of data/report.csv"

#### MySQL
- "Show me all tables in the database"
- "What's the schema of the users table?"
- "Get the first 10 rows from orders table"

#### JIRA
- "Show me open issues in project PROJ"
- "Get details for issue PROJ-123"
- "Create a new bug with title 'Login not working'"

#### Shopify
- "Show me all products"
- "Get orders from last week"
- "What's the inventory level for product 12345?"

#### Google Workspace
- "Show me my recent Google Docs"
- "List my spreadsheets"
- "What's on my calendar today?"
- "Search for emails from john@example.com"
- "Create a new document called 'Meeting Notes'"

## Testing

### Backend Tests

```bash
cd backend
pytest tests/ -v --cov=app
```

### MCP Connector Tests

```bash
# S3
cd connectors/s3
pytest tests/ -v

# MySQL
cd connectors/mysql
pytest tests/ -v

# JIRA
cd connectors/jira
pytest tests/ -v

# Shopify
cd connectors/shopify
pytest tests/ -v
```

### Frontend Tests

```bash
cd frontend
npm test
```

## Development

### Project Structure

```
ConnectorMCP/
├── frontend/              # React TypeScript frontend
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── services/     # API clients
│   │   └── types/        # TypeScript types
│   └── package.json
│
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api/         # API routes
│   │   ├── core/        # Core functionality
│   │   ├── models/      # Pydantic models
│   │   └── services/    # Business logic
│   └── requirements.txt
│
├── connectors/          # MCP connector services
│   ├── s3/             # S3 connector
│   ├── mysql/          # MySQL connector
│   ├── jira/           # JIRA connector
│   ├── shopify/        # Shopify connector
│   └── google_workspace/ # Google Workspace connector
│
├── docs/               # Additional documentation
├── ARCHITECTURE.md     # Architecture documentation
└── README.md          # This file
```

### Adding a New Data Source

1. Create a new directory in `connectors/`
2. Implement MCP server with tools and resources
3. Add tests
4. Update `backend/app/services/mcp_service.py`
5. Add icon and UI elements in frontend
6. Update documentation

## Exporting Connectors

Each MCP connector is designed to be self-contained and exportable:

```bash
# Copy connector directory
cp -r connectors/s3 /path/to/your/project/

# Install dependencies
cd /path/to/your/project/s3
pip install -e .

# Run standalone
python src/s3_server.py
```

## API Documentation

### REST API Endpoints

#### Chat

- `POST /api/chat/message` - Send a chat message
- `GET /api/chat/sessions` - List chat sessions
- `POST /api/chat/sessions` - Create new session
- `DELETE /api/chat/sessions/:id` - Delete session

#### Data Sources

- `GET /api/datasources` - List available data sources
- `GET /api/datasources/:id/test` - Test data source connection

Full API documentation available at http://localhost:8000/docs when running.

## Production Deployment

### Environment Setup

1. Set all required environment variables
2. Use production-grade secrets management
3. Configure proper CORS origins
4. Set up SSL/TLS certificates

### Docker Deployment

```bash
# Build images
docker-compose build

# Run in production mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Scaling Considerations

- Use managed MCP server pool for high concurrency
- Implement request queuing for rate-limited APIs
- Add Redis for session storage
- Use CDN for frontend assets
- Implement proper monitoring and logging

## Security

- Never commit `.env` file or credentials
- Use environment variables for all secrets
- Implement API authentication (not included in base version)
- Use read-only database users when possible
- Follow principle of least privilege for all API keys
- Regularly rotate credentials

## Troubleshooting

### Backend won't start

- Check Python version: `python --version` (should be 3.11+)
- Verify all dependencies are installed: `pip install -r backend/requirements.txt`
- Check environment variables in `.env`
- Check logs for specific errors

### Frontend won't start

- Check Node version: `node --version` (should be 18+)
- Clear node_modules: `rm -rf node_modules && npm install`
- Check if port 5173 is available

### MCP Connection Errors

- Verify connector paths in `backend/app/services/mcp_service.py`
- Check connector dependencies are installed
- Verify data source credentials are correct
- Test connection using `/api/datasources/:id/test` endpoint

### Claude API Errors

- Verify `ANTHROPIC_API_KEY` is set correctly
- Check API rate limits and usage
- Ensure your API key has access to Claude Sonnet 4.5

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run all tests and linting
5. Submit a pull request

## License

[To be determined]

## Acknowledgments

- Built with [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- Powered by [Anthropic Claude](https://www.anthropic.com/)
- Frontend built with [React](https://react.dev/) and [Vite](https://vitejs.dev/)
- Backend built with [FastAPI](https://fastapi.tiangolo.com/)

## Support

For issues, questions, or contributions, please open an issue on GitHub.

## Roadmap

- [ ] Add vector database integration for semantic search
- [ ] Support for multi-source queries
- [ ] Query history and favorites
- [ ] Data visualization for query results
- [ ] Export functionality for query results
- [ ] Scheduled queries and alerts
- [ ] Additional data source connectors
- [ ] Authentication and user management
- [ ] Team collaboration features
- [ ] Query templates and snippets

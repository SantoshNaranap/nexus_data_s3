# ConnectorMCP - Quick Reference

## 🚀 Quick Start Commands

```bash
# Start Backend
cd backend && python -m app.main

# Start Frontend
cd frontend && npm run dev

# Run Tests
cd backend && python quick_test.py

# Access Application
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## 📁 Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/chat_service.py` | Main chat orchestration |
| `backend/app/services/mcp_service.py` | MCP connector management |
| `frontend/src/components/ChatInterface.tsx` | Chat UI component |
| `frontend/src/services/api.ts` | API client |
| `connectors/*/src/*_server.py` | MCP connector servers |
| `.env` | Environment variables |

## 🔧 Common Tasks

### Add New Data Source
1. Create `connectors/newsource/src/newsource_server.py`
2. Add to `backend/app/services/mcp_service.py`
3. Add icon in `frontend/src/components/ChatInterface.tsx`

### Debug Backend
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"Debug: {variable}")
```

### Debug Frontend
```typescript
console.log('Debug:', variable)
```

### Check Logs
```bash
# Backend output
tail -f backend/logs/app.log

# Or check running process
docker-compose logs -f backend
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 8000 in use | `lsof -ti:8000 \| xargs kill -9` |
| Port 5173 in use | `lsof -ti:5173 \| xargs kill -9` |
| Module not found | `pip install -r requirements.txt` |
| MCP connection error | Check connector path and env vars |
| Claude API error | Verify ANTHROPIC_API_KEY in .env |

## 📊 Architecture Overview

```
Frontend (React)
    ↓ HTTP/SSE
Backend (FastAPI)
    ↓ MCP Protocol (stdio)
Connectors (MCP Servers)
    ↓ Native APIs
Data Sources (S3, MySQL, etc.)
```

## 🔑 Environment Variables

```env
# Required
ANTHROPIC_API_KEY=sk-ant-xxx

# Optional (configure as needed)
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
MYSQL_HOST=localhost
MYSQL_USER=user
MYSQL_PASSWORD=password
MYSQL_DATABASE=database
```

## 🧪 Testing

```bash
# Quick verification
cd backend && python quick_test.py

# Full test suite
cd backend && python test_connectors.py

# Unit tests
cd backend && pytest tests/ -v

# Connector tests
cd connectors/s3 && pytest tests/ -v
```

## 📝 API Endpoints

```http
POST /api/chat/message              # Non-streaming chat
POST /api/chat/message/stream       # Streaming chat (SSE)
GET  /api/datasources               # List data sources
GET  /api/datasources/:id/test      # Test connection
GET  /api/chat/sessions             # List sessions
POST /api/chat/sessions             # Create session
DELETE /api/chat/sessions/:id       # Delete session
GET  /health                        # Health check
```

## 🎯 Key Features

- ✅ Natural language queries
- ✅ Character-by-character streaming
- ✅ Context-aware conversations
- ✅ Auto-parameter injection
- ✅ Smart query construction
- ✅ Multi-source switching

## 🔒 Security Notes

- Never commit `.env` file
- Use read-only DB users
- Rotate API keys regularly
- Only SELECT queries allowed in MySQL
- Input validation on all parameters

## 📚 Documentation

- Full guide: `DEVELOPER_GUIDE.md`
- Architecture: `ARCHITECTURE.md`
- Quick start: `QUICKSTART.md`
- User guide: `README.md`

## 🆘 Need Help?

1. Check `DEVELOPER_GUIDE.md`
2. Review error logs
3. Check MCP connector output
4. Verify environment variables
5. Test individual connectors

## 💡 Pro Tips

- Use `--reload` for backend development
- Frontend has hot reload by default
- Each connector is reusable independently
- Streaming buffers 2 chars for smoothness
- Claude handles multi-step reasoning automatically

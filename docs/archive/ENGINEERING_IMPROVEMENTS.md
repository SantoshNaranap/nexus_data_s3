# Engineering Improvements - Google/Apple Standards Implementation

**Date:** December 12, 2025
**Status:** Implemented

This document summarizes all the engineering improvements made to bring the ConnectorMCP codebase up to Google/Apple production standards.

---

## Summary of Changes

| Category | Status | Files Created/Modified |
|----------|--------|----------------------|
| Custom Exceptions | ✅ Complete | `app/core/exceptions.py` |
| Enums (Magic Strings) | ✅ Complete | `app/core/enums.py` |
| Structured Logging | ✅ Complete | `app/core/logging.py` |
| Cache Service | ✅ Complete | `app/core/cache.py` |
| Rate Limiting | ✅ Complete | `app/middleware/rate_limit.py` |
| Metrics Collection | ✅ Complete | `app/core/metrics.py` |
| Input Validation | ✅ Complete | `app/core/validation.py` |
| Health Endpoints | ✅ Complete | `app/api/health.py` |
| Security Fixes | ✅ Complete | `app/core/config.py`, `app/api/auth.py` |
| Test Suite | ✅ Complete | `tests/` directory |
| Main App Integration | ✅ Complete | `app/main.py` |

---

## 1. Custom Exception Hierarchy (`app/core/exceptions.py`)

### Purpose
Replace generic `Exception` catching with structured, typed exceptions that:
- Have consistent error codes
- Map to appropriate HTTP status codes
- Include safe-to-expose error messages
- Capture detailed context for debugging

### Key Classes
```python
AppError (base class)
├── AuthenticationError (401)
│   ├── TokenMissingError
│   ├── TokenInvalidError
│   ├── TokenExpiredError
│   └── UserNotFoundError
├── AuthorizationError (403)
├── ValidationError (400)
│   ├── InvalidDatasourceError
│   └── MissingCredentialsError
├── ResourceNotFoundError (404)
├── ExternalServiceError (502)
│   ├── ToolExecutionError
│   ├── MCPConnectionError
│   └── AnthropicAPIError
├── RateLimitError (429)
├── TimeoutError (504)
└── DatabaseError (500)
```

### Usage
```python
from app.core.exceptions import ValidationError, ToolExecutionError

# Raise structured error
raise ValidationError(
    message="Invalid datasource",
    details={"datasource": "unknown"}
)

# In API handler - automatic JSON response
@app.exception_handler(AppError)
async def app_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(include_details=not settings.is_production)
    )
```

---

## 2. Enums for Type Safety (`app/core/enums.py`)

### Purpose
Replace magic strings with type-safe enums for:
- IDE autocompletion
- Compile-time error detection
- Centralized constant management

### Key Enums
```python
DataSourceType     # slack, jira, mysql, s3, etc.
MessageRole        # user, assistant, system
AgentStepType      # thinking, tool_call, complete, etc.
RoutingPath        # direct, haiku, sonnet
CacheType          # tools, results, schema, session
ClaudeModel        # Model identifiers
SSEEventType       # Server-Sent Event types
```

### Tool Name Enums
```python
SlackTools.LIST_CHANNELS     # "list_channels"
JiraTools.QUERY_JIRA         # "query_jira"
MySQLTools.EXECUTE_QUERY     # "execute_query"
```

### Limits and TTLs
```python
CacheTTL.TOOLS = 300         # 5 minutes
CacheTTL.RESULTS = 30        # 30 seconds
Limits.MAX_MESSAGE_LENGTH = 100000
Limits.MAX_TOOL_ITERATIONS = 25
```

---

## 3. Structured Logging (`app/core/logging.py`)

### Purpose
Replace basic logging with structured, context-aware logging for:
- Request tracing
- Metrics correlation
- Log aggregation (ELK, Splunk, CloudWatch)

### Features
- **Context variables**: Automatic request_id, user_id, datasource propagation
- **JSON format**: For production log aggregation
- **Readable format**: For development
- **Specialized loggers**: PerformanceLogger, SecurityLogger

### Usage
```python
from app.core.logging import get_logger, set_request_context, perf_logger

logger = get_logger(__name__)

# Set context at request start
set_request_context(request_id="abc123", user_id="user-456")

# Log with extra fields
logger.info("Processing message", extra={
    "datasource": "slack",
    "tool": "list_channels",
    "duration_ms": 150
})

# Performance logging
perf_logger.log_tool_execution(
    tool_name="list_channels",
    datasource="slack",
    duration_ms=150,
    cached=True
)
```

---

## 4. Cache Service (`app/core/cache.py`)

### Purpose
Replace global mutable state with a proper cache service that:
- Uses LRU eviction
- Supports TTL-based expiration
- Is thread-safe
- Can be backed by Redis in production

### Features
```python
cache = get_cache_service()

# Tool definitions cache (5 min TTL)
cache.set_tools("slack", tools)
cache.get_tools("slack")

# Result cache (30 sec TTL)
cache.set_result("slack", "list_channels", {"limit": 100}, result)
cache.get_result("slack", "list_channels", {"limit": 100})

# Schema cache (10 min TTL)
cache.set_schema("users", schema)

# Session cache
cache.append_to_session("session-123", message)
```

### Statistics
```python
stats = cache.get_stats()
# {"hits": 150, "misses": 20, "hit_rate": 0.882, "size": 45}
```

---

## 5. Rate Limiting (`app/middleware/rate_limit.py`)

### Purpose
Protect against:
- DoS attacks
- API abuse
- Credential stuffing

### Algorithm
Sliding window counter (more accurate than fixed window)

### Configuration
```python
# In config.py
rate_limit_enabled: bool = True
rate_limit_requests_per_minute: int = 60
rate_limit_requests_per_hour: int = 1000
```

### Response Headers
```
X-RateLimit-Limit-Minute: 60
X-RateLimit-Remaining-Minute: 45
Retry-After: 30  # If rate limited
```

### Endpoint-Specific Limits
```python
@router.post("/expensive")
@rate_limit(requests_per_minute=10)
async def expensive_operation():
    ...
```

---

## 6. Metrics Collection (`app/core/metrics.py`)

### Purpose
Provide observability through:
- Request metrics
- Tool execution metrics
- LLM usage metrics
- Cache performance
- Error tracking

### Available Metrics
```python
metrics = get_metrics()

# Counters
metrics.requests_total
metrics.chat_messages_total
metrics.tool_calls_total
metrics.cache_hits
metrics.errors_total

# Histograms
metrics.request_duration
metrics.chat_response_time
metrics.tool_duration
metrics.llm_duration

# Gauges
metrics.active_connections
metrics.active_streams
```

### Prometheus Export
```
GET /health/metrics

# HELP mosaic_requests_total Total number of requests
# TYPE mosaic_requests_total counter
mosaic_requests_total{method="GET",endpoint="/api/chat",status="200"} 150
```

---

## 7. Input Validation (`app/core/validation.py`)

### Purpose
Validate all user inputs to prevent:
- SQL injection
- XSS attacks
- Invalid data
- Buffer overflow

### Features
```python
validator = get_validator()

# Validate chat request
result = validator.validate_chat_request(
    message="Hello",
    datasource="slack",
    session_id="abc123"
)

# Pydantic models with validation
request = ValidatedChatRequest(
    message=message,
    datasource=datasource
)
```

### Security Checks
```python
check_sql_injection("SELECT * FROM users")  # True (suspicious)
check_xss("<script>alert(1)</script>")      # True (suspicious)
sanitize_html("<p>Hello</p>")               # "Hello"
```

---

## 8. Health Check Endpoints (`app/api/health.py`)

### Endpoints
```
GET /health           # Basic health (liveness)
GET /health/live      # Kubernetes liveness probe
GET /health/ready     # Kubernetes readiness probe
GET /health/detailed  # Full system status
GET /health/config    # Configuration check (no secrets)
GET /health/metrics   # Prometheus metrics
```

### Readiness Checks
- Database connectivity
- Cache service
- Required configuration

---

## 9. Security Fixes

### Config Changes (`app/core/config.py`)
```python
# Configurable frontend URL (not hardcoded)
frontend_url: str = "http://localhost:5173"

# Environment-aware cookie settings
cookie_secure: bool = False      # True in production
cookie_samesite: str = "lax"     # "strict" in production

@property
def cookie_settings(self) -> dict:
    if self.is_production:
        return {"secure": True, "samesite": "strict", "httponly": True}
    return {...}
```

### Auth Fixes (`app/api/auth.py`)
```python
# Uses configured URL instead of hardcoded
frontend_url = settings.frontend_url

# Proper cookie settings
cookie_settings = settings.cookie_settings
response.set_cookie(
    key="access_token",
    value=access_token,
    httponly=cookie_settings["httponly"],
    secure=cookie_settings["secure"],
    samesite=cookie_settings["samesite"],
)
```

---

## 10. Test Suite

### Structure
```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_exceptions.py   # Exception hierarchy tests
│   ├── test_cache.py        # Cache service tests
│   ├── test_validation.py   # Input validation tests
│   └── test_metrics.py      # Metrics tests
├── integration/
│   ├── test_health_api.py   # Health endpoint tests
│   └── test_auth_api.py     # Auth endpoint tests
└── requirements-test.txt    # Test dependencies
```

### Running Tests
```bash
pip install -r tests/requirements-test.txt
pytest tests/ -v --cov=app
```

---

## 11. Main App Integration (`app/main.py`)

### Changes
1. **Structured logging initialization**
2. **Cache service initialization**
3. **Metrics middleware** (captures all requests)
4. **Rate limiting middleware**
5. **Request context middleware** (adds request_id)
6. **AppError exception handler**
7. **Health router integration**

### Middleware Order (outermost to innermost)
1. MetricsMiddleware
2. RateLimitMiddleware
3. SessionMiddleware
4. CORSMiddleware
5. RequestContextMiddleware

---

## Remaining Items (Lower Priority)

| Item | Priority | Notes |
|------|----------|-------|
| Dependency Injection | Medium | Full DI container for testability |
| Method Refactoring | Medium | Break down large methods (>40 lines) |
| React Error Boundaries | Low | Frontend error handling |
| CI/CD Pipeline | Low | GitHub Actions for tests |

---

## Environment Variables for Production

```bash
# Required for production
ENVIRONMENT=production
FRONTEND_URL=https://app.example.com
COOKIE_SECURE=true
RATE_LIMIT_ENABLED=true

# Optional Redis for caching
REDIS_URL=redis://redis:6379
USE_REDIS_CACHE=true
```

---

## Verification

All new components have been verified:
```
✓ All new modules imported successfully
✓ Exception hierarchy working
✓ Enums working
✓ Cache service working
✓ Metrics working
✓ Validation working
✓ Rate limiter working
```

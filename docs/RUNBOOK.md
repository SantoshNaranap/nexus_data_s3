# ConnectorMCP Operations Runbook

## Service Architecture

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (ALB/nginx)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐ ┌────▼────┐ ┌───────▼────────┐
     │  Backend API   │ │ Backend │ │   Backend API  │
     │  Instance 1    │ │ Inst. 2 │ │   Instance N   │
     └────────┬───────┘ └────┬────┘ └───────┬────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐        ┌─────▼─────┐       ┌─────▼─────┐
    │  MySQL  │        │   Redis   │       │ MCP       │
    │ (State) │        │  (Cache)  │       │ Connectors│
    └─────────┘        └───────────┘       └───────────┘
```

## Health Check Endpoints

### Primary Health Check
```bash
GET /health
```

**Expected Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Deep Health Check
```bash
GET /api/health
```

Checks database connectivity and returns detailed status.

## Common Failure Modes and Remediation

### 1. Database Connection Issues

**Symptoms:**
- 500 errors on most API endpoints
- Health check returns "unhealthy"
- Logs show `SQLAlchemyError` or connection timeout

**Diagnosis:**
```bash
# Check database connectivity
mysql -h $LOCAL_MYSQL_HOST -u $LOCAL_MYSQL_USER -p$LOCAL_MYSQL_PASSWORD -e "SELECT 1"

# Check connection pool status
curl -s localhost:8000/api/health | jq '.database'
```

**Remediation:**
1. Verify database is running and accessible
2. Check connection limits: `SHOW STATUS LIKE 'Threads_connected'`
3. Restart backend if connection pool is exhausted
4. Scale database connections if needed

### 2. MCP Connector Failures

**Symptoms:**
- Chat responses fail for specific datasources
- "Tool call failed" errors in logs
- Circuit breaker opens for a datasource

**Diagnosis:**
```bash
# Check circuit breaker state
curl -s localhost:8000/api/health | jq '.mcp_connectors'

# Check MCP connector logs
grep "MCP" /var/log/connectormcp/app.log | tail -100
```

**Remediation:**
1. Check if external service (Slack/GitHub/Jira) is operational
2. Verify credentials are still valid
3. Wait for circuit breaker to reset (automatic)
4. Manual reset: restart the backend instance

### 3. Rate Limit Issues

**Symptoms:**
- Users receiving 429 responses
- Legitimate traffic being blocked

**Diagnosis:**
```bash
# Check current rate limit settings
curl -s localhost:8000/api/health | jq '.rate_limit'

# Check Redis rate limit keys (if using Redis backend)
redis-cli keys "ratelimit:*" | head -20
```

**Remediation:**
1. Increase rate limits in config if legitimate traffic
2. Identify and block abusive IPs at load balancer
3. Check if single user is hitting limits (investigate usage)

### 4. OAuth Flow Failures

**Symptoms:**
- Users cannot connect datasources
- "Invalid state" errors after OAuth redirect

**Diagnosis:**
```bash
# Check OAuth state table
mysql -e "SELECT COUNT(*) as states, MAX(expires_at) as latest FROM oauth_states" connectorMCP

# Check expired states (should be cleaned up)
mysql -e "SELECT COUNT(*) as expired FROM oauth_states WHERE expires_at < NOW()" connectorMCP
```

**Remediation:**
1. Ensure database is properly storing OAuth states
2. Check clock sync between instances (NTP)
3. Increase OAuth state TTL if flows are timing out
4. Clean up expired states: `DELETE FROM oauth_states WHERE expires_at < NOW()`

### 5. High Memory Usage

**Symptoms:**
- Container OOMKilled
- Slow response times
- Increased swap usage

**Diagnosis:**
```bash
# Check memory usage
docker stats connectormcp-backend

# Check for memory leaks in logs
grep -i "memory" /var/log/connectormcp/app.log
```

**Remediation:**
1. Restart affected instances
2. Increase container memory limits
3. Review recent code changes for memory leaks
4. Check for runaway MCP connections

## Scaling Guidelines

### Horizontal Scaling (Add Instances)

When to scale:
- Response time p99 > 500ms
- CPU usage consistently > 70%
- Active connections approaching limit

Requirements for multi-instance:
- Redis backend for rate limiting (`RATE_LIMIT_BACKEND=redis`)
- Database-backed OAuth states (already implemented)
- Sticky sessions NOT required (stateless API)

### Vertical Scaling (Increase Resources)

| Load Level | CPU | Memory | Connections |
|------------|-----|--------|-------------|
| Light (< 100 RPM) | 0.5 vCPU | 512MB | 10 |
| Medium (100-1000 RPM) | 1 vCPU | 1GB | 50 |
| Heavy (> 1000 RPM) | 2+ vCPU | 2GB+ | 100+ |

## Log Analysis Queries

### Find Error Patterns
```bash
# Count errors by type (last hour)
grep "ERROR" /var/log/connectormcp/app.log | \
  grep -oP '"error_type":\s*"\K[^"]+' | \
  sort | uniq -c | sort -rn

# Find slow requests (> 5 seconds)
grep "duration_ms" /var/log/connectormcp/app.log | \
  awk -F'duration_ms' '{print $2}' | \
  awk '$1 > 5000 {print}' | head -20
```

### Find Authentication Issues
```bash
# Failed auth attempts
grep "auth_failure\|invalid_token\|unauthorized" /var/log/connectormcp/app.log | \
  tail -100
```

### Find Rate Limit Hits
```bash
# Rate limited requests
grep "rate_limit_exceeded" /var/log/connectormcp/app.log | \
  grep -oP '"client_ip":\s*"\K[^"]+' | \
  sort | uniq -c | sort -rn | head -20
```

## Environment Variables Reference

### Required in Production
| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Deployment environment | `production` |
| `JWT_SECRET_KEY` | JWT signing key (64+ chars) | `<generated>` |
| `ENCRYPTION_KEY` | Credential encryption key | `<fernet-key>` |
| `LOCAL_MYSQL_HOST` | Database hostname | `db.example.com` |
| `LOCAL_MYSQL_PASSWORD` | Database password | `<secret>` |

### Optional Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_BACKEND` | Rate limit backend | `memory` |
| `TRUSTED_PROXIES` | Trusted proxy IPs | `""` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Tracing endpoint | `""` |

## Emergency Procedures

### Complete Service Restart
```bash
# Graceful restart (rolling)
kubectl rollout restart deployment/connectormcp-backend

# Force restart (all pods)
kubectl delete pods -l app=connectormcp-backend
```

### Database Recovery
```bash
# Point-in-time recovery
# 1. Stop all backend instances
# 2. Restore database from backup
# 3. Apply binary logs to recovery point
# 4. Start backend instances
```

### Rollback Deployment
```bash
# Kubernetes
kubectl rollout undo deployment/connectormcp-backend

# Docker Compose
docker-compose pull && docker-compose up -d --no-deps backend
```

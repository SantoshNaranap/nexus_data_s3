# ConnectorMCP Security Audit Checklist

## Pre-Deployment Security Review

### 1. Authentication Verification

#### JWT Configuration
- [ ] JWT secret key is at least 64 characters
- [ ] JWT secret is unique per environment
- [ ] Token expiration is appropriately set (default: 24 hours)
- [ ] Tokens are transmitted only via HTTPOnly cookies

```bash
# Verify JWT secret length
echo $JWT_SECRET_KEY | wc -c  # Should be > 64

# Check token in response headers (should NOT appear)
curl -v https://api.example.com/api/auth/login 2>&1 | grep -i "authorization"
```

#### OAuth Security
- [ ] OAuth state is stored in database (not in-memory)
- [ ] State tokens expire after 10 minutes
- [ ] State tokens are one-time use (deleted after validation)
- [ ] Redirect URIs are strictly validated

```sql
-- Check OAuth states aren't accumulating
SELECT COUNT(*) FROM oauth_states WHERE expires_at < NOW();
-- Should be 0 or very low
```

#### Session Security
- [ ] Session IDs use cryptographically secure generation
- [ ] Session comparison uses timing-safe comparison
- [ ] Sessions are invalidated on logout
- [ ] Session timeout is configured (24 hours)

### 2. Credential Encryption Validation

#### Encryption Keys
- [ ] ENCRYPTION_KEY is set and valid Fernet key
- [ ] Key is at least 32 bytes (44 chars base64)
- [ ] Key rotation is configured (ENCRYPTION_KEY_V1)
- [ ] Keys are not committed to version control

```bash
# Verify key is valid Fernet format
python3 -c "from cryptography.fernet import Fernet; Fernet(b'$ENCRYPTION_KEY')"

# Check for keys in git history
git log -p --all -S 'ENCRYPTION_KEY' -- . | head -20
```

#### Credential Storage
- [ ] Credentials are encrypted at rest
- [ ] Encrypted format includes version prefix (v2:)
- [ ] Decryption errors are handled gracefully
- [ ] No plaintext credentials in logs

```sql
-- Verify credentials are encrypted (should see v2: prefix or encrypted blob)
SELECT LEFT(encrypted_credentials, 20) FROM user_credentials LIMIT 5;
```

### 3. Rate Limit Testing

#### Configuration
- [ ] Rate limiting is enabled in production
- [ ] Limits are appropriate for expected traffic
- [ ] Trusted proxies are correctly configured
- [ ] Redis backend is used for multi-instance

```bash
# Test rate limiting
for i in {1..100}; do
  curl -s -o /dev/null -w "%{http_code}\n" https://api.example.com/health
done | sort | uniq -c
# Should see 429s after limit reached
```

#### IP Validation
- [ ] X-Forwarded-For only trusted from configured proxies
- [ ] Direct client IP is used when not from proxy
- [ ] Spoofed headers are ignored

```bash
# Test header spoofing (should not bypass rate limit)
curl -H "X-Forwarded-For: 1.2.3.4" https://api.example.com/api/chat/message
```

### 4. CORS Policy Review

#### Configuration
- [ ] CORS origins are explicitly listed
- [ ] Wildcards are not used in production
- [ ] Credentials flag matches cookie usage
- [ ] Preflight caching is appropriate

```bash
# Check CORS headers
curl -v -H "Origin: https://evil.com" https://api.example.com/api/health 2>&1 | grep -i "access-control"
# Should NOT include evil.com in allowed origins
```

### 5. Dependency Vulnerability Scanning

#### Automated Scanning
- [ ] pip-audit or safety is run in CI/CD
- [ ] No critical vulnerabilities in dependencies
- [ ] Dependencies are pinned to specific versions
- [ ] Outdated packages are tracked

```bash
# Scan for vulnerabilities
pip-audit

# Check for outdated packages
pip list --outdated
```

#### Manual Review
- [ ] Review changelogs for security-related updates
- [ ] Check for known CVEs in major dependencies
- [ ] Verify transitive dependencies

### 6. API Security

#### Input Validation
- [ ] All inputs are validated via Pydantic models
- [ ] SQL injection is prevented (parameterized queries)
- [ ] XSS is prevented (proper encoding)
- [ ] Path traversal is prevented

#### Error Handling
- [ ] Stack traces are not exposed in production
- [ ] Error messages don't leak sensitive info
- [ ] All errors are logged for investigation

```bash
# Check error response format
curl -s https://api.example.com/api/nonexistent | jq
# Should not contain stack trace or internal paths
```

### 7. Logging Security

#### Log Content
- [ ] Passwords are never logged
- [ ] API keys/tokens are masked
- [ ] PII is handled according to policy
- [ ] Request IDs enable correlation

```bash
# Search logs for sensitive patterns
grep -iE "(password|secret|token|api_key)" /var/log/app.log
# Should return masked values or nothing
```

#### Log Access
- [ ] Logs are not publicly accessible
- [ ] Log retention policy is configured
- [ ] Log aggregation is encrypted in transit

### 8. Infrastructure Security

#### Network
- [ ] TLS 1.2+ is enforced
- [ ] HSTS is enabled
- [ ] Internal services are not publicly accessible

#### Secrets Management
- [ ] Secrets are stored in secrets manager (not env files)
- [ ] Secret rotation is possible without downtime
- [ ] Access to secrets is audited

### 9. MCP Connector Security

#### Connection Security
- [ ] Connector credentials are encrypted
- [ ] Timeouts are configured (30 seconds)
- [ ] Circuit breakers prevent cascade failures
- [ ] Error responses don't leak connector details

### 10. Database Security

#### Access Control
- [ ] Database user has minimal required permissions
- [ ] Connection uses TLS
- [ ] Connection strings don't appear in logs

#### Data Protection
- [ ] Sensitive data is encrypted
- [ ] Backup encryption is enabled
- [ ] Point-in-time recovery is configured

## Periodic Security Tasks

### Weekly
- [ ] Review authentication failure logs
- [ ] Check rate limit abuse patterns
- [ ] Review new dependency versions

### Monthly
- [ ] Run full vulnerability scan
- [ ] Review access logs for anomalies
- [ ] Test backup restoration
- [ ] Review and rotate API keys

### Quarterly
- [ ] Penetration testing
- [ ] Security policy review
- [ ] Incident response drill
- [ ] Key rotation

## Security Incident Indicators

### Watch For
- Unusual authentication failure patterns
- Rate limit violations from single sources
- OAuth flow errors (possible CSRF attacks)
- Credential decryption failures
- Unexpected API access patterns

### Response
See [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) for incident handling procedures.

## Compliance Checklist

### OWASP Top 10 Coverage
- [x] A01 Broken Access Control - JWT + role-based access
- [x] A02 Cryptographic Failures - Fernet encryption
- [x] A03 Injection - Parameterized queries
- [x] A04 Insecure Design - Security reviews
- [x] A05 Security Misconfiguration - Production defaults
- [x] A06 Vulnerable Components - Dependency scanning
- [x] A07 Auth Failures - Secure session management
- [x] A08 Software Integrity - CI/CD controls
- [x] A09 Logging Failures - Structured logging
- [x] A10 SSRF - Input validation

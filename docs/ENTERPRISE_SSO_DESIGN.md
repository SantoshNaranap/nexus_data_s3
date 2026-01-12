# Enterprise SSO Integration Design

## Overview

This document outlines the architecture for enabling single sign-on (SSO) authentication where users log in once with their company email and automatically gain access to all their connected data sources (Slack, GitHub, Jira, Google Workspace, etc.).

## Current State

Today, ConnectorMCP requires:
1. Users to manually configure credentials for each data source
2. Each connector needs its own OAuth token or API key
3. No centralized identity management
4. Credentials stored per-user in the database

## Target State

Users should be able to:
1. Log in with their company email (e.g., `user@company.com`)
2. Automatically access all data sources their company has connected
3. No manual credential configuration per connector
4. Single logout terminates all sessions

---

## Architecture Options

### Option 1: OAuth with Identity Provider (Recommended)

Use a corporate Identity Provider (IdP) like Google Workspace, Microsoft Entra ID (Azure AD), or Okta.

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Flow                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   User ──► ConnectorMCP ──► Identity Provider (Google/Okta)     │
│              │                      │                            │
│              │                      ▼                            │
│              │              User Authenticates                   │
│              │              (company email)                      │
│              │                      │                            │
│              ◄──────────────────────┘                            │
│              │                                                   │
│              ▼                                                   │
│   User Session Created                                           │
│   (linked to company tenant)                                     │
│              │                                                   │
│              ▼                                                   │
│   Access Company's Pre-configured                                │
│   Data Source Connections                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**How it works:**
1. Admin configures IdP integration (Google Workspace, Okta, etc.)
2. Admin connects company data sources ONCE (Slack workspace, GitHub org, etc.)
3. Users log in with company email via IdP
4. System identifies user's company/tenant from email domain
5. User automatically gets access to company's connected data sources

### Option 2: SAML 2.0 Federation

For enterprises requiring SAML-based authentication.

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   User       │ ───► │ ConnectorMCP │ ───► │  Company     │
│   Browser    │      │   (SP)       │      │  IdP (SAML)  │
└──────────────┘      └──────────────┘      └──────────────┘
                             │
                             ▼
                      SAML Assertion
                      (email, groups)
                             │
                             ▼
                      Map to Tenant
                      & Permissions
```

### Option 3: Email Domain-Based Multi-Tenancy

Simpler approach using email domain to determine tenant.

```
user@acme.com      ──► Tenant: ACME Corp     ──► ACME's Slack, GitHub, etc.
user@globex.com    ──► Tenant: Globex Inc    ──► Globex's Slack, GitHub, etc.
```

---

## Recommended Implementation

### Phase 1: Google Workspace OAuth (Start Here)

Most companies use Google Workspace. Start with Google OAuth.

#### 1.1 Backend Changes

**New tables:**

```sql
-- Tenants/Organizations
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,  -- e.g., "acme.com"
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tenant-level data source connections (admin-configured)
CREATE TABLE tenant_datasources (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    datasource VARCHAR(50) NOT NULL,      -- "slack", "github", etc.
    credentials JSONB NOT NULL,            -- encrypted OAuth tokens
    config JSONB,                          -- workspace ID, org name, etc.
    connected_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, datasource)
);

-- Users belong to tenants
ALTER TABLE users ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'member';  -- 'admin' or 'member'
```

**New API endpoints:**

```python
# Auth endpoints
POST /api/auth/google          # Initiate Google OAuth
GET  /api/auth/google/callback # Handle OAuth callback
POST /api/auth/logout          # End session

# Admin endpoints (tenant admins only)
GET  /api/admin/datasources           # List tenant's connected sources
POST /api/admin/datasources/{type}/connect    # Connect a data source
DELETE /api/admin/datasources/{type}  # Disconnect a data source

# User endpoints
GET /api/datasources           # List available data sources (from tenant)
```

#### 1.2 Authentication Flow

```python
# Pseudo-code for Google OAuth callback

async def google_callback(code: str):
    # 1. Exchange code for tokens
    tokens = await google_oauth.exchange_code(code)

    # 2. Get user info
    user_info = await google_oauth.get_user_info(tokens.access_token)
    email = user_info["email"]  # e.g., "john@acme.com"

    # 3. Extract domain and find/create tenant
    domain = email.split("@")[1]  # "acme.com"
    tenant = await get_or_create_tenant(domain)

    # 4. Find/create user in tenant
    user = await get_or_create_user(
        email=email,
        name=user_info["name"],
        tenant_id=tenant.id
    )

    # 5. Create session
    session = await create_session(user.id)

    # 6. Return session token
    return {"token": session.token, "user": user}
```

#### 1.3 Data Source Access

When a user queries a data source:

```python
async def get_datasource_credentials(user_id: str, datasource: str):
    # 1. Get user's tenant
    user = await get_user(user_id)
    tenant_id = user.tenant_id

    # 2. Get tenant's credentials for this datasource
    tenant_ds = await get_tenant_datasource(tenant_id, datasource)

    if not tenant_ds:
        raise HTTPException(404, f"{datasource} not connected for your organization")

    # 3. Return decrypted credentials
    return decrypt_credentials(tenant_ds.credentials)
```

### Phase 2: Admin Dashboard

Build an admin interface for tenant admins to:

1. **Connect Data Sources**
   - OAuth flow for Slack, GitHub, Google Workspace, Jira
   - API key input for others (MySQL, S3)

2. **Manage Users**
   - View users in tenant
   - Assign admin/member roles
   - Revoke access

3. **View Usage**
   - Query history
   - Data source usage stats

```
┌─────────────────────────────────────────────────────────────┐
│  ConnectorMCP Admin Dashboard                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Connected Data Sources                                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ ✓ Slack │ │ ✓ GitHub│ │ ✓ Jira  │ │ + Add   │           │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
│                                                             │
│  Team Members (5)                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ john@acme.com        Admin    Last active: Today     │  │
│  │ jane@acme.com        Member   Last active: Yesterday │  │
│  │ bob@acme.com         Member   Last active: 3 days    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 3: Additional IdP Support

Add support for other identity providers:

1. **Microsoft Entra ID (Azure AD)**
   - For Microsoft 365 companies
   - OIDC/OAuth flow similar to Google

2. **Okta**
   - Enterprise SSO
   - SAML or OIDC

3. **Generic SAML**
   - For any SAML 2.0 compliant IdP

---

## Data Source OAuth Flows

Each data source needs its own OAuth integration for the ADMIN to connect:

### Slack
```
Admin clicks "Connect Slack"
    ──► Redirect to Slack OAuth
    ──► Admin authorizes for workspace
    ──► Receive workspace token
    ──► Store as tenant's Slack credentials
```

**Required Slack Scopes (Bot Token):**
- `channels:history`, `channels:read`
- `groups:history`, `groups:read`
- `im:history`, `im:read`
- `users:read`, `users:read.email`

### GitHub
```
Admin clicks "Connect GitHub"
    ──► Redirect to GitHub OAuth
    ──► Admin authorizes for org
    ──► Receive org token
    ──► Store as tenant's GitHub credentials
```

**Required GitHub Scopes:**
- `repo` (for private repos)
- `read:org`

### Google Workspace
```
Admin clicks "Connect Google Workspace"
    ──► Redirect to Google OAuth (admin consent)
    ──► Domain-wide delegation setup
    ──► Access all users' Drive, Calendar, Gmail
```

### Jira
```
Admin clicks "Connect Jira"
    ──► Redirect to Atlassian OAuth
    ──► Admin authorizes
    ──► Receive Jira Cloud token
    ──► Store as tenant's Jira credentials
```

---

## Security Considerations

### 1. Credential Storage

```python
# Encrypt credentials at rest
from cryptography.fernet import Fernet

def encrypt_credentials(credentials: dict, key: bytes) -> str:
    f = Fernet(key)
    return f.encrypt(json.dumps(credentials).encode()).decode()

def decrypt_credentials(encrypted: str, key: bytes) -> dict:
    f = Fernet(key)
    return json.loads(f.decrypt(encrypted.encode()))
```

### 2. Token Refresh

```python
# Background job to refresh OAuth tokens before expiry
async def refresh_expiring_tokens():
    expiring = await get_tokens_expiring_soon(hours=1)
    for token in expiring:
        new_token = await refresh_oauth_token(token)
        await update_token(token.id, new_token)
```

### 3. Audit Logging

```python
# Log all data access
async def log_access(user_id: str, datasource: str, action: str):
    await audit_log.create(
        user_id=user_id,
        datasource=datasource,
        action=action,
        timestamp=datetime.utcnow()
    )
```

### 4. Role-Based Access

```python
# Only admins can connect/disconnect data sources
@require_role("admin")
async def connect_datasource(tenant_id: str, datasource: str):
    ...
```

---

## Implementation Checklist

### Backend
- [ ] Add tenant and tenant_datasources tables
- [ ] Implement Google OAuth login
- [ ] Add tenant detection from email domain
- [ ] Create admin API endpoints for data source management
- [ ] Implement credential encryption/decryption
- [ ] Add token refresh background job
- [ ] Implement audit logging

### Frontend
- [ ] Add "Sign in with Google" button
- [ ] Create admin dashboard for data source management
- [ ] Show connected data sources to users
- [ ] Add user management UI for admins

### Data Source Integrations
- [ ] Slack OAuth flow for workspace connection
- [ ] GitHub OAuth flow for org connection
- [ ] Jira OAuth flow
- [ ] Google Workspace OAuth with domain-wide delegation

### DevOps
- [ ] Set up encryption key management (AWS KMS, HashiCorp Vault)
- [ ] Configure OAuth app credentials per environment
- [ ] Set up token refresh cron job

---

## Quick Start: Google OAuth Setup

### 1. Create Google OAuth App

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Go to **APIs & Services > Credentials**
4. Click **Create Credentials > OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Add authorized redirect URI: `https://your-domain.com/api/auth/google/callback`
7. Save Client ID and Client Secret

### 2. Configure Backend

```bash
# .env
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://your-domain.com/api/auth/google/callback
```

### 3. Install Dependencies

```bash
pip install authlib httpx
```

### 4. Implement OAuth Endpoint

```python
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@router.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')

    # Extract domain, find/create tenant and user
    email = user_info['email']
    domain = email.split('@')[1]

    tenant = await get_or_create_tenant(domain)
    user = await get_or_create_user(email, user_info['name'], tenant.id)

    # Create session and return token
    session_token = create_jwt(user.id, tenant.id)

    # Redirect to frontend with token
    return RedirectResponse(f"{FRONTEND_URL}?token={session_token}")
```

---

## Summary

The recommended approach is:

1. **Start with Google OAuth** - Most companies use Google Workspace
2. **Multi-tenant by email domain** - `@acme.com` users → Acme tenant
3. **Admin connects data sources once** - Stored at tenant level
4. **All tenant users get access** - No per-user credential setup

This gives you enterprise-grade SSO with minimal friction for end users while maintaining security and proper access controls.

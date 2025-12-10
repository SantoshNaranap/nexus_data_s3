# Mosaic Deployment Guide

Deploy Mosaic to **Vercel** (Frontend) + **Railway** (Backend)

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Vercel       │────▶│    Railway      │────▶│  MySQL (Railway)│
│   (Frontend)    │     │   (Backend)     │     │  or PlanetScale │
│   React + Vite  │     │   FastAPI       │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Prerequisites

- GitHub account with your code pushed
- [Railway account](https://railway.app) (free tier available)
- [Vercel account](https://vercel.com) (free tier available)
- Anthropic API key

---

## Step 1: Deploy Backend to Railway

### 1.1 Create Railway Project

1. Go to [Railway](https://railway.app) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository
4. Choose the `backend` folder as root directory (or deploy from monorepo)

### 1.2 Add MySQL Database

1. In your Railway project, click **"+ New"** → **"Database"** → **"MySQL"**
2. Railway will create a MySQL instance and provide connection details
3. Note the connection variables (they'll be auto-injected)

### 1.3 Configure Environment Variables

In Railway, go to your service → **Variables** and add:

```
# Required
ENVIRONMENT=production
ANTHROPIC_API_KEY=sk-ant-xxxxx
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
ENCRYPTION_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Database (Railway auto-provides these, but verify names match)
LOCAL_MYSQL_HOST=${{MySQL.MYSQLHOST}}
LOCAL_MYSQL_PORT=${{MySQL.MYSQLPORT}}
LOCAL_MYSQL_USER=${{MySQL.MYSQLUSER}}
LOCAL_MYSQL_PASSWORD=${{MySQL.MYSQLPASSWORD}}
LOCAL_MYSQL_DATABASE=${{MySQL.MYSQLDATABASE}}

# CORS (add your Vercel URL after deploying frontend)
CORS_ORIGINS=https://your-app.vercel.app

# Connector credentials (add as needed)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-token
```

### 1.4 Deploy Settings

Railway should auto-detect the Dockerfile. Verify:
- **Build Command**: Uses Dockerfile
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Root Directory**: `backend` (if monorepo)

### 1.5 Get Your Backend URL

After deployment, Railway provides a URL like:
```
https://mosaic-backend-production.up.railway.app
```

**Save this URL** - you'll need it for the frontend.

---

## Step 2: Deploy Frontend to Vercel

### 2.1 Create Vercel Project

1. Go to [Vercel](https://vercel.com) and sign in with GitHub
2. Click **"Add New"** → **"Project"**
3. Import your repository
4. Configure:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

### 2.2 Configure Environment Variables

In Vercel project settings → **Environment Variables**:

```
VITE_API_URL=https://your-backend.railway.app
```

Replace with your actual Railway backend URL from Step 1.5.

### 2.3 Deploy

Click **Deploy**. Vercel will build and deploy your frontend.

Your app will be available at:
```
https://your-app.vercel.app
```

---

## Step 3: Update CORS Configuration

Go back to Railway and update the `CORS_ORIGINS` variable:

```
CORS_ORIGINS=https://your-app.vercel.app,https://your-custom-domain.com
```

Railway will automatically redeploy.

---

## Step 4: Configure Google OAuth (Optional)

If using Google authentication:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create OAuth 2.0 credentials
3. Add authorized redirect URIs:
   - `https://your-backend.railway.app/api/auth/google/callback`
4. Add to Railway environment variables:
   ```
   GOOGLE_OAUTH_CLIENT_ID=your-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   ```

---

## Quick Reference: Environment Variables

### Backend (Railway)

| Variable | Required | Description |
|----------|----------|-------------|
| `ENVIRONMENT` | Yes | Set to `production` |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `JWT_SECRET_KEY` | Yes | JWT signing key |
| `ENCRYPTION_KEY` | Yes | Fernet encryption key |
| `LOCAL_MYSQL_*` | Yes | App database connection |
| `CORS_ORIGINS` | Yes | Frontend URLs (comma-separated) |
| `AWS_ACCESS_KEY_ID` | No | S3 connector |
| `AWS_SECRET_ACCESS_KEY` | No | S3 connector |
| `JIRA_URL` | No | JIRA connector |
| `JIRA_EMAIL` | No | JIRA connector |
| `JIRA_API_TOKEN` | No | JIRA connector |

### Frontend (Vercel)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes | Railway backend URL |

---

## Generate Secrets

```bash
# JWT Secret Key
openssl rand -hex 32

# Encryption Key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Troubleshooting

### CORS Errors
- Verify `CORS_ORIGINS` in Railway includes your Vercel URL
- Ensure no trailing slashes in URLs

### Database Connection Errors
- Check Railway MySQL is running
- Verify environment variable names match config.py expectations

### 502 Bad Gateway
- Check Railway logs: `railway logs`
- Ensure PORT is not hardcoded (use `$PORT`)

### Build Failures
- Frontend: Check Node version (should be 18+)
- Backend: Check Python version (should be 3.11+)

---

## Custom Domain Setup

### Vercel (Frontend)
1. Project Settings → Domains
2. Add your custom domain
3. Update DNS records as instructed

### Railway (Backend)
1. Service Settings → Networking → Custom Domain
2. Add your API domain (e.g., `api.yourdomain.com`)
3. Update DNS records as instructed
4. Update `CORS_ORIGINS` to include new domains

---

## Cost Estimate

| Service | Free Tier | Paid |
|---------|-----------|------|
| Railway | $5/month credit | ~$10-20/month |
| Vercel | 100GB bandwidth | ~$20/month pro |
| Railway MySQL | Included | Included |

Total: **Free** to start, ~$10-40/month for production use

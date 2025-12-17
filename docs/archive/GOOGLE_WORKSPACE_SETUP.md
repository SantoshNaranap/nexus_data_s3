# Google Workspace MCP Connector - Setup Guide

This guide will help you set up Google OAuth 2.0 credentials to enable the Google Workspace connector.

---

## 📋 What You'll Get

Once configured, you can chat with:
- **Google Docs** - Read, write, and format documents
- **Google Sheets** - Query and manipulate spreadsheets
- **Google Drive** - List, search, and manage files
- **Gmail** - Read and search emails
- **Google Calendar** - View and manage events
- **And more...**

---

## 🔧 Setup Steps

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **"Select a Project"** → **"New Project"**
3. Enter project name (e.g., "ConnectorMCP")
4. Click **"Create"**

### Step 2: Enable Required APIs

In your Google Cloud project, enable these APIs:

1. Go to **"APIs & Services"** → **"Library"**
2. Search for and enable each of these:
   - ✅ Google Docs API
   - ✅ Google Sheets API
   - ✅ Google Drive API
   - ✅ Gmail API
   - ✅ Google Calendar API
   - ✅ Google Forms API
   - ✅ Google Tasks API
   - ✅ Google Chat API
   - ✅ Google Slides API

**Quick Enable:** Search "Google Workspace APIs" and enable the bundle.

### Step 3: Create OAuth 2.0 Credentials

1. Go to **"APIs & Services"** → **"Credentials"**
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. If prompted, configure the OAuth consent screen:
   - User Type: **External** (for testing) or **Internal** (for organization)
   - Fill in required fields:
     - App name: `ConnectorMCP`
     - User support email: Your email
     - Developer contact: Your email
   - Click **"Save and Continue"**

4. Add Scopes (click "Add or Remove Scopes"):
   ```
   https://www.googleapis.com/auth/documents
   https://www.googleapis.com/auth/drive
   https://www.googleapis.com/auth/spreadsheets
   https://www.googleapis.com/auth/gmail.readonly
   https://www.googleapis.com/auth/calendar
   https://www.googleapis.com/auth/forms
   https://www.googleapis.com/auth/tasks
   ```

5. Add Test Users (if using External user type):
   - Add your Google email address
   - Click **"Save and Continue"**

6. Back to Credentials page:
   - Click **"Create Credentials"** → **"OAuth client ID"**
   - Application type: **Desktop app**
   - Name: `ConnectorMCP Desktop`
   - Click **"Create"**

7. **Download the credentials:**
   - You'll see a popup with your Client ID and Client Secret
   - **Copy both values** - you'll need them for `.env`

### Step 4: Configure Environment Variables

1. Open your `.env` file (or create from `.env.example`)
2. Add your Google OAuth credentials:

```env
# Google Workspace Configuration
GOOGLE_OAUTH_CLIENT_ID=your_actual_client_id_here.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your_actual_client_secret_here
USER_GOOGLE_EMAIL=your_email@gmail.com
```

**Example:**
```env
GOOGLE_OAUTH_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-abc123xyz789
USER_GOOGLE_EMAIL=john.doe@gmail.com
```

### Step 5: Install Dependencies

The Google Workspace connector requires additional Python packages:

```bash
cd /Users/santoshnaranapatty/ConnectorMCP/connectors/google_workspace
pip install -r requirements.txt
```

Or if using `uv`:
```bash
cd /Users/santoshnaranapatty/ConnectorMCP/connectors/google_workspace
uv pip install -e .
```

### Step 6: First Run - OAuth Authorization

The first time you use the Google Workspace connector, you'll need to authorize it:

1. Start the backend:
```bash
cd /Users/santoshnaranapatty/ConnectorMCP/backend
python -m app.main
```

2. When you first send a message to Google Workspace:
   - A browser window will open automatically
   - Sign in with your Google account
   - Grant the requested permissions
   - The authorization will be saved in `~/.credentials/`

3. Future runs will use the saved credentials automatically

---

## 🧪 Testing the Connection

Once configured, test with these queries:

### Google Docs
```
"Show me my recent Google Docs"
"Create a new document called 'Meeting Notes'"
"What's in my document titled 'Project Plan'?"
```

### Google Sheets
```
"List my spreadsheets"
"Show me data from 'Sales Report' sheet"
"What's in cell A1 of my Budget spreadsheet?"
```

### Google Drive
```
"What files do I have in Drive?"
"Search for PDFs in my Drive"
"Show me files modified today"
```

### Gmail
```
"Show me my recent emails"
"Search for emails from john@example.com"
"How many unread emails do I have?"
```

### Google Calendar
```
"What's on my calendar today?"
"Show me meetings this week"
"Do I have any events tomorrow?"
```

---

## 🔒 Security Notes

### Credentials Storage
- OAuth credentials are stored in `~/.credentials/google_workspace/`
- **NEVER commit this directory to Git**
- **NEVER commit your `.env` file**

### Token Refresh
- Access tokens expire after 1 hour
- Refresh tokens are used to get new access tokens automatically
- If you see authentication errors, delete `~/.credentials/` and re-authorize

### Scopes
The connector uses these scopes (permissions):
- **Read-only** for Gmail (cannot send/delete emails)
- **Full access** for Docs, Sheets, Drive (can create/edit/delete)
- **Read/Write** for Calendar (can create/edit events)

---

## 🐛 Troubleshooting

### "Invalid Client ID"
- ✅ Check your `GOOGLE_OAUTH_CLIENT_ID` in `.env`
- ✅ Make sure you copied the full ID including `.apps.googleusercontent.com`
- ✅ Verify the OAuth client type is "Desktop app"

### "Access Denied" or "Insufficient Permissions"
- ✅ Make sure you added all required scopes in OAuth consent screen
- ✅ Delete `~/.credentials/google_workspace/` and re-authorize
- ✅ Check that your email is added as a test user

### "API Not Enabled"
- ✅ Enable the required Google APIs in Cloud Console
- ✅ Wait a few minutes for APIs to activate

### "redirect_uri_mismatch"
- ✅ Use "Desktop app" type (not "Web application")
- ✅ Desktop apps don't require redirect URI configuration

### Browser Doesn't Open for Authorization
- ✅ Manual authorization URL will be printed in console
- ✅ Copy and paste the URL into your browser
- ✅ After authorization, copy the code back to console

---

## 📊 What's Available

### Core Tools (Included)
- Google Docs: Create, read, edit, format documents
- Google Sheets: Read, write, query spreadsheet data
- Google Drive: List, search, read files
- Google Calendar: View, create, edit events
- Gmail: Read, search emails

### Extended Tools (Optional)
To enable all tools, change in `mcp_service.py`:
```python
"--tool-tier", "complete"  # Instead of "core"
```

This adds:
- Google Forms: Create and manage forms
- Google Tasks: Manage task lists
- Google Chat: Send messages to Chat spaces
- Google Slides: Create and edit presentations
- Google Search: Programmable Search Engine

---

## 🎯 Quick Reference

**Environment Variables Required:**
```env
GOOGLE_OAUTH_CLIENT_ID=your_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
USER_GOOGLE_EMAIL=your_email@gmail.com
```

**Location of Credentials:**
- OAuth config: `~/.credentials/google_workspace/credentials.json`
- Token: `~/.credentials/google_workspace/token.json`

**Connector Path:**
- `/Users/santoshnaranapatty/ConnectorMCP/connectors/google_workspace/`

**Backend Configuration:**
- `/Users/santoshnaranapatty/ConnectorMCP/backend/app/services/mcp_service.py`

---

## ✅ Verification Checklist

Before testing, make sure:
- [ ] Google Cloud Project created
- [ ] All required APIs enabled
- [ ] OAuth 2.0 credentials created (Desktop app)
- [ ] Client ID and Secret added to `.env`
- [ ] Email address added to `.env`
- [ ] Dependencies installed
- [ ] Backend restarted after config changes

---

## 🆘 Need Help?

1. Check the [Google Workspace MCP Server GitHub](https://github.com/taylorwilsdon/google_workspace_mcp)
2. Review [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
3. Check backend logs: `tail -f backend/logs/app.log`

---

**Last Updated:** November 25, 2025

# Quick Start Guide - ConnectorMCP

Get ConnectorMCP running in under 5 minutes!

## Prerequisites Check

Before starting, ensure you have:

- [ ] Python 3.11 or higher: `python --version`
- [ ] Node.js 18 or higher: `node --version`
- [ ] Anthropic API key from https://console.anthropic.com/

## Step 1: Environment Setup (2 minutes)

```bash
# Clone/navigate to the project
cd ConnectorMCP

# Copy environment template
cp .env.example .env

# Edit .env and add your Anthropic API key
# Minimum required:
# ANTHROPIC_API_KEY=sk-ant-...
```

## Step 2: Backend Setup (1 minute)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Start the backend
python -m app.main
```

You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Step 3: Frontend Setup (2 minutes)

Open a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start the frontend
npm run dev
```

You should see:
```
  VITE v5.0.11  ready in XXX ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

## Step 4: Access the Application

Open your browser to: **http://localhost:5173**

You should see the ConnectorMCP interface with data sources in the sidebar!

## Step 5: Test with S3 (if you have AWS credentials)

If you have AWS credentials, add them to `.env`:

```bash
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=us-east-1
```

Restart the backend, then in the UI:
1. Click on "Amazon S3" in the sidebar
2. Try: "List all my buckets"
3. Or: "Show me what data sources are available"

## Using Without Data Source Credentials

Even without specific data source credentials, you can:
1. Explore the UI and interface
2. See the chat functionality
3. View the architecture
4. Run tests

The app will show which data sources are available based on your credentials.

## Common Issues

### Backend won't start

**Error**: ModuleNotFoundError
```bash
# Make sure you're in the backend directory
cd backend
pip install -r requirements.txt
```

**Error**: Port already in use
```bash
# Kill the process on port 8000
lsof -ti:8000 | xargs kill -9
```

### Frontend won't start

**Error**: Cannot find module
```bash
# Clear and reinstall
rm -rf node_modules package-lock.json
npm install
```

**Error**: Port already in use
```bash
# Kill the process on port 5173
lsof -ti:5173 | xargs kill -9
```

### Anthropic API Error

**Error**: Invalid API key
- Double check your API key in `.env`
- Make sure there are no extra spaces or quotes
- Verify the key starts with `sk-ant-`

## Next Steps

### Add More Data Sources

1. **MySQL**: Add MySQL credentials to `.env`
   ```bash
   MYSQL_HOST=localhost
   MYSQL_USER=myuser
   MYSQL_PASSWORD=mypassword
   MYSQL_DATABASE=mydatabase
   ```

2. **JIRA**: Add JIRA credentials to `.env`
   ```bash
   JIRA_URL=https://your-domain.atlassian.net
   JIRA_EMAIL=your@email.com
   JIRA_API_TOKEN=your_token
   ```

3. **Shopify**: Add Shopify credentials to `.env`
   ```bash
   SHOPIFY_SHOP_URL=your-shop.myshopify.com
   SHOPIFY_ACCESS_TOKEN=your_token
   ```

Restart the backend after adding credentials.

### Run Tests

```bash
# Backend tests
cd backend
pytest tests/ -v

# Individual connector tests
cd connectors/s3
pytest tests/ -v
```

### Use Docker (Alternative Setup)

```bash
# From project root
docker-compose up
```

This starts everything in containers!

## Getting Help

- Check `README.md` for full documentation
- Review `ARCHITECTURE.md` for system design
- Open an issue on GitHub for bugs

## What You Can Ask

### General Questions
- "What data sources are available?"
- "Show me what you can do"

### S3 (if configured)
- "List all my buckets"
- "Show files in bucket-name"
- "Read the file data/report.csv"

### MySQL (if configured)
- "Show all tables"
- "What's the schema of users table?"
- "Get 10 rows from orders"

### JIRA (if configured)
- "Show open issues"
- "Get issue PROJECT-123"
- "List all projects"

### Shopify (if configured)
- "Show all products"
- "Get recent orders"
- "Check inventory levels"

## Success Checklist

- [x] Backend running on port 8000
- [x] Frontend running on port 5173
- [x] Can access http://localhost:5173
- [x] See data sources in sidebar
- [x] Can click on a data source
- [x] Can send a message in chat
- [x] Receive a response from Claude

Congratulations! You're now running ConnectorMCP! 🎉

# Authentication Quick Start Guide

## Quick Setup (5 minutes)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Check Configuration
Verify your `.env` file has these variables:
```bash
cat .env | grep -E "(MYSQL|GOOGLE|JWT)"
```

Should show:
- MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
- GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
- JWT_SECRET_KEY, JWT_ALGORITHM

### 3. Initialize Database
```bash
python -m app.init_db
```

Expected output:
```
INFO - Starting database initialization...
INFO - Database tables created successfully!
INFO - Tables created: users, chat_history
```

### 4. Test Setup
```bash
python test_auth.py
```

Expected output:
```
Results: 5/5 tests passed
✓ All tests passed! Authentication system is ready.
```

### 5. Start Application
```bash
uvicorn app.main:app --reload --port 8000
```

Visit: http://localhost:8000/docs to see API documentation

## Quick Examples

### Protect a Route

```python
from fastapi import APIRouter, Depends
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/my-protected-route")
async def my_route(current_user: User = Depends(get_current_user)):
    return {
        "message": f"Hello {current_user.name}",
        "email": current_user.email
    }
```

### Access Database in Route

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User, ChatHistory

@router.post("/save-chat")
async def save_chat(
    message: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Create chat history
    chat = ChatHistory(
        user_id=current_user.id,
        datasource="mysql",
        messages=[{"role": "user", "content": message}]
    )
    db.add(chat)
    await db.commit()

    return {"status": "saved"}
```

### Frontend Login Flow

```javascript
// 1. Redirect to Google OAuth
window.location.href = 'http://localhost:8000/api/auth/google';

// 2. After callback, check auth status
const response = await fetch('http://localhost:8000/api/auth/me', {
    credentials: 'include'  // Important!
});

if (response.ok) {
    const user = await response.json();
    console.log('Logged in as:', user.email);
}

// 3. Logout
await fetch('http://localhost:8000/api/auth/logout', {
    method: 'POST',
    credentials: 'include'
});
```

## Common Issues & Fixes

### Issue: "Database connection failed"
```bash
# Check MySQL is running and credentials are correct
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD -e "SELECT 1"
```

### Issue: "JWT token validation failed"
```bash
# Verify JWT_SECRET_KEY is set and at least 32 characters
echo $JWT_SECRET_KEY | wc -c
```

### Issue: "Google OAuth redirect failed"
1. Check Google Cloud Console → APIs & Services → Credentials
2. Add authorized redirect URI: `http://localhost:8000/api/auth/callback`
3. Verify OAuth consent screen is configured

### Issue: "CORS error"
Add frontend URL to CORS_ORIGINS in `.env`:
```
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

## Testing Endpoints

### Using curl

```bash
# 1. Get auth URL (manually follow redirect in browser)
curl -v http://localhost:8000/api/auth/google

# 2. After login, check user info (with cookie)
curl -b cookies.txt http://localhost:8000/api/auth/me

# 3. Or use Authorization header
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8000/api/auth/me
```

### Using Python

```python
import requests

# Login would be done in browser
# After login, use cookie or token:

session = requests.Session()
response = session.get('http://localhost:8000/api/auth/me')
print(response.json())
```

## Database Commands

```bash
# Create tables
python -m app.init_db

# Reset database (DELETE ALL DATA!)
python -m app.init_db --reset

# Connect to database
mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE

# Check tables
mysql> SHOW TABLES;
mysql> DESCRIBE users;
mysql> SELECT * FROM users;
```

## Environment Variables Reference

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| MYSQL_HOST | Yes | localhost | MySQL host |
| MYSQL_PORT | Yes | 3306 | MySQL port |
| MYSQL_USER | Yes | admin | MySQL username |
| MYSQL_PASSWORD | Yes | password | MySQL password |
| MYSQL_DATABASE | Yes | mosaic_db | Database name |
| GOOGLE_OAUTH_CLIENT_ID | Yes | 123...apps.googleusercontent.com | Google OAuth client ID |
| GOOGLE_OAUTH_CLIENT_SECRET | Yes | GOCSPX-... | Google OAuth secret |
| JWT_SECRET_KEY | Yes | your-secret-key | JWT signing key (32+ chars) |
| JWT_ALGORITHM | No | HS256 | JWT algorithm |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | No | 1440 | Token expiration (24h) |
| CORS_ORIGINS | No | http://localhost:5173 | Allowed CORS origins |

## API Quick Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/google` | GET | No | Start OAuth flow |
| `/api/auth/callback` | GET | No | OAuth callback |
| `/api/auth/me` | GET | Yes | Get current user |
| `/api/auth/logout` | POST | No | Logout |
| `/api/auth/status` | GET | Optional | Check auth status |

## Next Steps

1. Run `python test_auth.py` to verify setup
2. Start the app: `uvicorn app.main:app --reload`
3. Visit http://localhost:8000/docs for API docs
4. Test login at http://localhost:8000/api/auth/google
5. Check authenticated endpoints work

For detailed documentation, see `AUTH_SETUP.md`

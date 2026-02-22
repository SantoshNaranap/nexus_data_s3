"""
Pytest configuration and fixtures for ConnectorMCP tests.

Provides common fixtures for testing:
- Mock services
- Test database
- Authenticated users
- Sample data
"""

import asyncio
import os
import sys
from typing import AsyncGenerator, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.database import get_db
from app.models.database import Base, User


# ============ Event Loop ============


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============ Database Fixtures ============


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def override_get_db(test_db: AsyncSession):
    """Override the database dependency."""

    async def _get_db():
        yield test_db

    return _get_db


# ============ Client Fixtures ============


@pytest.fixture
async def client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with overridden dependencies."""
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(
    client: AsyncClient,
    test_user: User,
) -> AsyncClient:
    """Create an authenticated test client."""
    # Set authentication cookie
    from app.services.auth_service import auth_service

    token = auth_service.create_access_token(
        data={"user_id": test_user.id, "email": test_user.email}
    )
    client.cookies.set("access_token", token)
    return client


# ============ User Fixtures ============


@pytest.fixture
async def test_user(test_db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id="test-user-123",
        email="test@example.com",
        password_hash="$2b$12$test_hash_for_testing_only",
        name="Test User",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest.fixture
def sample_user_data() -> Dict:
    """Sample user data for testing."""
    return {
        "id": "user-456",
        "email": "sample@example.com",
        "password_hash": "$2b$12$sample_hash_for_testing",
        "name": "Sample User",
        "profile_picture": "https://example.com/pic.jpg",
    }


# ============ Mock Fixtures ============


@pytest.fixture
def mock_anthropic():
    """Mock the Anthropic client."""
    with patch("app.services.chat_service.Anthropic") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client

        # Mock messages.create
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)
        mock_client.messages.create.return_value = mock_response

        yield mock_client


@pytest.fixture
def mock_mcp_service():
    """Mock the MCP service."""
    with patch("app.services.mcp_service.MCPService") as mock:
        mock_service = AsyncMock()

        # Mock tool listing
        mock_service.get_tools.return_value = [
            {
                "name": "list_channels",
                "description": "List Slack channels",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

        # Mock tool execution
        mock_service.call_tool.return_value = {"channels": ["general", "random"]}

        yield mock_service


@pytest.fixture
def mock_credential_service():
    """Mock the credential service."""
    with patch("app.services.credential_service.credential_service") as mock:
        mock.get_credentials = AsyncMock(
            return_value={"api_key": "test-key"}
        )
        mock.save_credentials = AsyncMock()
        mock.has_credentials = AsyncMock(return_value=True)
        yield mock


# ============ Sample Data Fixtures ============


@pytest.fixture
def sample_chat_request() -> Dict:
    """Sample chat request data."""
    return {
        "message": "Show me the channels",
        "datasource": "slack",
        "session_id": "test-session-123",
    }


@pytest.fixture
def sample_credentials() -> Dict:
    """Sample credentials data."""
    return {
        "datasource": "slack",
        "credentials": {
            "slack_bot_token": "xoxb-test-token",
            "slack_user_token": "xoxp-test-token",
        },
    }


@pytest.fixture
def sample_tool_response() -> Dict:
    """Sample MCP tool response."""
    return {
        "channels": [
            {"id": "C123", "name": "general", "is_private": False},
            {"id": "C456", "name": "random", "is_private": False},
        ]
    }


# ============ Environment Fixtures ============


@pytest.fixture(autouse=True)
def set_test_environment(monkeypatch):
    """Set test environment variables."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0xMjM0NTY3ODkwMTIzNA==")


# ============ Helper Functions ============


def create_mock_tool_use_block(name: str, input_data: Dict) -> MagicMock:
    """Create a mock tool use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    block.id = f"tool-{name}-123"
    return block


def create_mock_text_block(text: str) -> MagicMock:
    """Create a mock text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block

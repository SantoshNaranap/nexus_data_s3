"""Tests for Shopify MCP Server."""

import json
import pytest
from unittest.mock import patch, MagicMock
import responses


@pytest.fixture
def mock_shopify_env(monkeypatch):
    """Mock Shopify environment variables."""
    monkeypatch.setenv("SHOPIFY_SHOP_URL", "test-shop.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("SHOPIFY_API_VERSION", "2024-01")


@pytest.mark.asyncio
@responses.activate
async def test_list_products(mock_shopify_env):
    """Test listing products."""
    from shopify_server import handle_list_products

    # Mock API response
    responses.add(
        responses.GET,
        "https://test-shop.myshopify.com/admin/api/2024-01/products.json",
        json={
            "products": [
                {
                    "id": 1,
                    "title": "Product 1",
                    "status": "active",
                    "vendor": "Vendor A",
                    "product_type": "Type A",
                    "created_at": "2024-01-01",
                    "variants": [],
                }
            ]
        },
        status=200,
    )

    arguments = {"limit": 50}
    result = await handle_list_products(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 1
    assert data["products"][0]["title"] == "Product 1"


@pytest.mark.asyncio
@responses.activate
async def test_list_orders(mock_shopify_env):
    """Test listing orders."""
    from shopify_server import handle_list_orders

    responses.add(
        responses.GET,
        "https://test-shop.myshopify.com/admin/api/2024-01/orders.json",
        json={
            "orders": [
                {
                    "id": 1,
                    "order_number": 1001,
                    "total_price": "100.00",
                    "currency": "USD",
                    "financial_status": "paid",
                    "fulfillment_status": "fulfilled",
                    "created_at": "2024-01-01",
                    "line_items": [],
                    "customer": {"email": "test@test.com", "first_name": "John", "last_name": "Doe"},
                }
            ]
        },
        status=200,
    )

    arguments = {"limit": 50, "status": "any"}
    result = await handle_list_orders(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 1
    assert data["orders"][0]["order_number"] == 1001

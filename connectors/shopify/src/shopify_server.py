#!/usr/bin/env python3
"""
Shopify MCP Server

Provides MCP tools for interacting with Shopify stores.
"""

import json
import logging
import os
from typing import Any

import requests
from mcp.server import Server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shopify-mcp-server")

# Shopify configuration
SHOPIFY_SHOP_URL = os.getenv("SHOPIFY_SHOP_URL")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")

# Create MCP server
app = Server("shopify-connector")


def make_shopify_request(endpoint: str, method: str = "GET", data: dict | None = None) -> dict:
    """Make a request to Shopify API."""
    url = f"https://{SHOPIFY_SHOP_URL}/admin/api/{SHOPIFY_API_VERSION}/{endpoint}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }

    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data)
    elif method == "PUT":
        response = requests.put(url, headers=headers, json=data)
    else:
        raise ValueError(f"Unsupported method: {method}")

    response.raise_for_status()
    return response.json()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available Shopify tools."""
    return [
        Tool(
            name="list_products",
            description="List products from the Shopify store",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of products to return (default: 50, max: 250)",
                        "default": 50,
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status: active, archived, draft",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_product",
            description="Get details of a specific product",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID",
                    },
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="search_products",
            description="Search products by title or other criteria",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (searches in title, description, etc.)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_orders",
            description="List orders from the Shopify store",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of orders to return (default: 50, max: 250)",
                        "default": 50,
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status: open, closed, cancelled, any",
                        "default": "any",
                    },
                    "financial_status": {
                        "type": "string",
                        "description": "Filter by financial status: paid, pending, refunded, etc.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_order",
            description="Get details of a specific order",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID",
                    },
                },
                "required": ["order_id"],
            },
        ),
        Tool(
            name="get_inventory",
            description="Get inventory levels for products",
            inputSchema={
                "type": "object",
                "properties": {
                    "location_id": {
                        "type": "string",
                        "description": "Filter by location ID (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of items to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="list_customers",
            description="List customers from the Shopify store",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of customers to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "list_products":
            return await handle_list_products(arguments)
        elif name == "get_product":
            return await handle_get_product(arguments)
        elif name == "search_products":
            return await handle_search_products(arguments)
        elif name == "list_orders":
            return await handle_list_orders(arguments)
        elif name == "get_order":
            return await handle_get_order(arguments)
        elif name == "get_inventory":
            return await handle_get_inventory(arguments)
        elif name == "list_customers":
            return await handle_list_customers(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Shopify API Error: {str(e)}")]
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


async def handle_list_products(arguments: dict[str, Any]) -> list[TextContent]:
    """List products."""
    limit = arguments.get("limit", 50)
    status = arguments.get("status")

    params = f"limit={limit}"
    if status:
        params += f"&status={status}"

    data = make_shopify_request(f"products.json?{params}")

    products = [
        {
            "id": product["id"],
            "title": product["title"],
            "status": product["status"],
            "vendor": product["vendor"],
            "product_type": product["product_type"],
            "created_at": product["created_at"],
            "variants_count": len(product.get("variants", [])),
        }
        for product in data.get("products", [])
    ]

    result = {
        "count": len(products),
        "products": products,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_product(arguments: dict[str, Any]) -> list[TextContent]:
    """Get product details."""
    product_id = arguments["product_id"]
    data = make_shopify_request(f"products/{product_id}.json")

    product = data.get("product", {})
    result = {
        "id": product["id"],
        "title": product["title"],
        "description": product.get("body_html", ""),
        "status": product["status"],
        "vendor": product["vendor"],
        "product_type": product["product_type"],
        "tags": product["tags"],
        "variants": product.get("variants", []),
        "images": [{"src": img["src"], "alt": img.get("alt")} for img in product.get("images", [])],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_search_products(arguments: dict[str, Any]) -> list[TextContent]:
    """Search products."""
    query = arguments["query"]
    limit = arguments.get("limit", 50)

    data = make_shopify_request(f"products.json?limit={limit}&title={query}")

    products = [
        {
            "id": product["id"],
            "title": product["title"],
            "status": product["status"],
            "vendor": product["vendor"],
        }
        for product in data.get("products", [])
    ]

    result = {
        "query": query,
        "count": len(products),
        "products": products,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_list_orders(arguments: dict[str, Any]) -> list[TextContent]:
    """List orders."""
    limit = arguments.get("limit", 50)
    status = arguments.get("status", "any")
    financial_status = arguments.get("financial_status")

    params = f"limit={limit}&status={status}"
    if financial_status:
        params += f"&financial_status={financial_status}"

    data = make_shopify_request(f"orders.json?{params}")

    orders = [
        {
            "id": order["id"],
            "order_number": order["order_number"],
            "total_price": order["total_price"],
            "currency": order["currency"],
            "financial_status": order["financial_status"],
            "fulfillment_status": order.get("fulfillment_status"),
            "customer": {
                "email": order.get("customer", {}).get("email"),
                "name": f"{order.get('customer', {}).get('first_name', '')} {order.get('customer', {}).get('last_name', '')}".strip(),
            },
            "created_at": order["created_at"],
            "line_items_count": len(order.get("line_items", [])),
        }
        for order in data.get("orders", [])
    ]

    result = {
        "count": len(orders),
        "orders": orders,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_order(arguments: dict[str, Any]) -> list[TextContent]:
    """Get order details."""
    order_id = arguments["order_id"]
    data = make_shopify_request(f"orders/{order_id}.json")

    order = data.get("order", {})
    result = {
        "id": order["id"],
        "order_number": order["order_number"],
        "total_price": order["total_price"],
        "subtotal_price": order["subtotal_price"],
        "total_tax": order["total_tax"],
        "currency": order["currency"],
        "financial_status": order["financial_status"],
        "fulfillment_status": order.get("fulfillment_status"),
        "customer": order.get("customer", {}),
        "line_items": order.get("line_items", []),
        "shipping_address": order.get("shipping_address", {}),
        "created_at": order["created_at"],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_inventory(arguments: dict[str, Any]) -> list[TextContent]:
    """Get inventory levels."""
    limit = arguments.get("limit", 50)
    location_id = arguments.get("location_id")

    params = f"limit={limit}"
    if location_id:
        params += f"&location_ids={location_id}"

    data = make_shopify_request(f"inventory_levels.json?{params}")

    inventory = [
        {
            "inventory_item_id": item["inventory_item_id"],
            "location_id": item["location_id"],
            "available": item["available"],
            "updated_at": item["updated_at"],
        }
        for item in data.get("inventory_levels", [])
    ]

    result = {
        "count": len(inventory),
        "inventory_levels": inventory,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_list_customers(arguments: dict[str, Any]) -> list[TextContent]:
    """List customers."""
    limit = arguments.get("limit", 50)
    data = make_shopify_request(f"customers.json?limit={limit}")

    customers = [
        {
            "id": customer["id"],
            "email": customer["email"],
            "first_name": customer["first_name"],
            "last_name": customer["last_name"],
            "orders_count": customer["orders_count"],
            "total_spent": customer["total_spent"],
            "created_at": customer["created_at"],
        }
        for customer in data.get("customers", [])
    ]

    result = {
        "count": len(customers),
        "customers": customers,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def main():
    """Run the Shopify MCP server."""
    import asyncio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()

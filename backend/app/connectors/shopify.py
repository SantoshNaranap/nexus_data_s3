"""
Shopify connector configuration.

Provides MCP tools for interacting with Shopify stores:
- Products
- Orders
- Customers
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class ShopifyConnector(BaseConnector):
    """Shopify e-commerce connector configuration."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="shopify",
            name="Shopify",
            description="Query Shopify products, orders, and customers",
            icon="shopify",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        return [
            CredentialField(
                name="shopify_shop_url",
                env_var="SHOPIFY_SHOP_URL",
                display_name="Shop URL",
                description="Your Shopify store URL (e.g., your-store.myshopify.com)",
                required=True,
                sensitive=False,
            ),
            CredentialField(
                name="shopify_access_token",
                env_var="SHOPIFY_ACCESS_TOKEN",
                display_name="Access Token",
                description="Shopify Admin API access token",
                required=True,
            ),
            CredentialField(
                name="shopify_api_version",
                env_var="SHOPIFY_API_VERSION",
                display_name="API Version",
                description="Shopify API version (e.g., 2024-01)",
                required=False,
                sensitive=False,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/shopify/src/shopify_server.py"

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "list_products",
            "get_product",
            "list_orders",
            "get_order",
            "list_customers",
        ]

    @property
    def system_prompt_addition(self) -> str:
        return """
SHOPIFY TOOLS - COMPREHENSIVE GUIDE:

**PRIMARY TOOLS:**
- `list_products(limit)` - List ALL products in the store
- `get_product(product_id)` - Get detailed product info (variants, pricing, inventory)
- `list_orders(status, limit)` - List orders. Filter by status: open, closed, any
- `get_order(order_id)` - Get full order details with line items
- `list_customers(limit)` - List all customers
- `get_customer(customer_id)` - Get customer details and order history

**CRITICAL RULES - NEVER VIOLATE:**
1. ALWAYS call `list_products()` when asked about products/inventory
2. ALWAYS call `list_orders()` when asked about orders/sales
3. NEVER say "I don't have access" without calling a tool first
4. NEVER summarize as "you have 10 products" - show the actual products
5. ALWAYS show pricing, inventory, and status information

**WORKFLOW EXAMPLES:**

"Show my products" or "What do I sell?":
→ list_products()
→ Display ALL products with names, prices, and inventory

"Recent orders" or "Today's sales":
→ list_orders(status="any", limit=20)
→ Display ALL orders with customer names, amounts, status

"Unfulfilled orders" or "What needs shipping?":
→ list_orders(status="open")
→ Display ALL unfulfilled orders with shipping details

"Customer list" or "Who are my customers?":
→ list_customers()
→ Display ALL customers with names and order counts

"How is [product] selling?":
→ list_orders() + filter for that product
→ Show sales numbers and trends

"Order #[number]" or "Details on order [number]":
→ get_order(order_id)
→ Display FULL order with line items, customer, amounts

**DATA TO ALWAYS SHOW:**
- Products: name, price, inventory count, variants
- Orders: order number, customer, total, fulfillment status, items
- Customers: name, email, total orders, total spent

**NEVER DO THIS:**
- Don't say "store not configured" without trying a tool
- Don't summarize "you have orders" - show the actual orders
- Don't hide pricing or inventory data
- Don't refuse to show customer emails - they're the store owner's data
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common Shopify queries."""
        message_lower = message.lower().strip()

        if any(kw in message_lower for kw in ["product", "products", "item", "items", "inventory"]):
            return [{"tool": "list_products", "args": {}}]

        if any(kw in message_lower for kw in ["order", "orders", "sale", "sales"]):
            return [{"tool": "list_orders", "args": {}}]

        if any(kw in message_lower for kw in ["customer", "customers", "buyer", "buyers"]):
            return [{"tool": "list_customers", "args": {}}]

        return None


# Export singleton instance
shopify_connector = ShopifyConnector()

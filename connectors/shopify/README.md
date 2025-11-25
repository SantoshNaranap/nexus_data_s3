# Shopify MCP Connector

MCP server for Shopify integration, providing tools to manage products, orders, inventory, and customers.

## Features

- List and search products
- Get product details
- List and get orders
- Get inventory levels
- List customers

## Installation

```bash
cd connectors/shopify
pip install -e .
```

## Configuration

```bash
export SHOPIFY_SHOP_URL=your-shop.myshopify.com
export SHOPIFY_ACCESS_TOKEN=your_access_token
export SHOPIFY_API_VERSION=2024-01
```

## Running

```bash
python src/shopify_server.py
```

## Testing

```bash
pytest tests/
```

## License

[To be determined]

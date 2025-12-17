FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install connectors directly from GitHub (since they're in the same repo)
RUN pip install git+https://github.com/kaaylabs-v2/Mosaic.git#subdirectory=connectors/jira \
    && pip install git+https://github.com/kaaylabs-v2/Mosaic.git#subdirectory=connectors/s3 \
    && pip install git+https://github.com/kaaylabs-v2/Mosaic.git#subdirectory=connectors/mysql \
    && pip install git+https://github.com/kaaylabs-v2/Mosaic.git#subdirectory=connectors/shopify \
    && pip install git+https://github.com/kaaylabs-v2/Mosaic.git#subdirectory=connectors/slack \
    && pip install git+https://github.com/kaaylabs-v2/Mosaic.git#subdirectory=connectors/github_connector

# Copy application code
COPY . .

# Create connectors directory structure for MCP server paths
RUN mkdir -p /connectors

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

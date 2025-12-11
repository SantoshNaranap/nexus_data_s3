FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies for backend
RUN pip install --no-cache-dir -r requirements.txt

# Copy connectors source code
COPY connectors /connectors

# Install dependencies for each connector
# Note: Google Workspace connector has many dependencies, better to install them
RUN pip install -e /connectors/jira \
    && pip install -e /connectors/s3 \
    && pip install -e /connectors/mysql \
    && pip install -e /connectors/shopify \
    && pip install -e /connectors/google_workspace

# Copy application code
COPY backend/ .

# Copy connectors directory (needed for MCP connectors)
# Connectors are expected at /connectors in the container
COPY connectors /connectors

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

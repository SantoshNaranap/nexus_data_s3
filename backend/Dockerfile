FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy connectors and install them locally
COPY connectors /connectors
RUN pip install /connectors/jira \
    && pip install /connectors/s3 \
    && pip install /connectors/mysql \
    && pip install /connectors/shopify \
    && pip install /connectors/slack \
    && pip install /connectors/github

# Copy application code
COPY backend .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
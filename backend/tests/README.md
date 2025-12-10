# Test Files

This directory contains all test scripts for the ConnectorMCP backend.

## Test Categories

### Authentication Tests
- `test_auth.py` - Authentication flow tests
- `test_auth_and_credentials.py` - OAuth and credential storage tests

### Connector Tests
- `test_connectors.py` - Comprehensive S3 and MySQL connector tests
- `test_google_workspace.py` - Google Workspace integration tests

### JIRA Tests
- `test_jira_api.py` - JIRA API tests
- `test_jira_from_db.py` - JIRA queries using database credentials
- `test_jira_validation.py` - JIRA parameter validation tests
- `test_legacy_jira_tools.py` - Legacy JIRA tool tests
- `test_pm_queries.py` - PM-style natural language JIRA queries (16 tests)
- `test_query_jira.py` - Natural language query parser tests

### E2E Tests
- `test_e2e.py` - End-to-end tests
- `test_api_e2e.py` - API end-to-end tests

### Other Tests
- `test_credentials.py` - Credential management tests

## Running Tests

```bash
# Run all connector tests
python tests/test_connectors.py

# Run JIRA natural language tests
python tests/test_pm_queries.py

# Run auth and credential tests
python tests/test_auth_and_credentials.py
```

# JIRA MCP Connector

MCP server for JIRA integration, providing tools to manage issues, projects, and workflows.

## Features

- Search issues with JQL
- Get issue details
- Create new issues
- Update existing issues
- List and get projects
- Add comments to issues

## Installation

```bash
cd connectors/jira
pip install -e .
```

## Configuration

```bash
export JIRA_URL=https://your-domain.atlassian.net
export JIRA_EMAIL=your_email@example.com
export JIRA_API_TOKEN=your_api_token
```

## Running

```bash
python src/jira_server.py
```

## Testing

```bash
pytest tests/
```

## License

[To be determined]

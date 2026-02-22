"""
API v1 Router - Versioned API endpoints.

This module provides API versioning support. All endpoints are accessible
via both the legacy paths (/api/...) and versioned paths (/api/v1/...).

The versioning is implemented at the main.py level by mounting routers
at multiple paths. This file serves as documentation and potential
future extensibility point.

Version History:
- v1: Initial versioned API (2024-12-15)
  - Authentication with account lockout
  - Chat with pagination
  - Multi-source agent orchestration
  - Security headers and rate limiting
"""

# API version constant
VERSION = "v1"
VERSION_DATE = "2024-12-15"

# Changelog for this API version
CHANGELOG = """
## API v1 Changelog

### 2024-12-15: Initial Release
- Added account lockout after failed login attempts
- Added password complexity validation
- Added security headers middleware
- Added chat history pagination
- Added configurable rate limiting (user-based when authenticated)
- Added login attempt tracking for security auditing
"""


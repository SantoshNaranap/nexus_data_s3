"""
Error Investigation Service for automatic error diagnosis.

Automatically detects error patterns in chat responses, investigates root causes,
and reports findings to users.
"""

import asyncio
import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.circuit_breaker import mcp_circuit_breakers, CircuitState
from app.services.credential_service import credential_service
from app.services.mcp_service import mcp_service

logger = logging.getLogger(__name__)


class FindingCategory(str, Enum):
    """Categories of investigation findings."""
    CIRCUIT_BREAKER = "circuit_breaker"
    CREDENTIALS = "credentials"
    CONNECTION = "connection"
    MCP = "mcp"
    ERROR_PATTERN = "error_pattern"
    UNKNOWN = "unknown"


class FindingSeverity(str, Enum):
    """Severity levels for findings."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class InvestigationFinding:
    """A single finding from the investigation."""
    category: FindingCategory
    severity: FindingSeverity
    title: str
    detail: str
    suggested_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "detail": self.detail,
            "suggested_action": self.suggested_action,
        }


@dataclass
class ErrorInvestigationResponse:
    """Response from an error investigation."""
    investigation_id: str
    status: str
    root_cause: Optional[str]
    findings: List[InvestigationFinding]
    recommendations: List[str]
    investigated_at: str
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "status": self.status,
            "root_cause": self.root_cause,
            "findings": [f.to_dict() for f in self.findings],
            "recommendations": self.recommendations,
            "investigated_at": self.investigated_at,
            "duration_ms": self.duration_ms,
        }


# Error patterns to classify
ERROR_PATTERNS = {
    "auth_expired": {
        "patterns": ["token expired", "authentication failed", "401", "unauthorized", "access denied"],
        "category": FindingCategory.CREDENTIALS,
        "severity": FindingSeverity.CRITICAL,
        "title": "Authentication error detected",
        "detail": "The error message indicates an authentication or authorization issue",
        "action": "Reconnect your account in Settings",
    },
    "connection_failed": {
        "patterns": ["connection failed", "connection refused", "connection timed out", "network error"],
        "category": FindingCategory.CONNECTION,
        "severity": FindingSeverity.CRITICAL,
        "title": "Connection failure detected",
        "detail": "Unable to establish connection to the service",
        "action": "Check your network connection and try again",
    },
    "timeout": {
        "patterns": ["timed out", "timeout", "request timeout"],
        "category": FindingCategory.CONNECTION,
        "severity": FindingSeverity.WARNING,
        "title": "Request timeout detected",
        "detail": "The request took too long to complete",
        "action": "Try again - the service may be temporarily slow",
    },
    "service_unavailable": {
        "patterns": ["service unavailable", "503", "server error", "internal error"],
        "category": FindingCategory.CONNECTION,
        "severity": FindingSeverity.WARNING,
        "title": "Service temporarily unavailable",
        "detail": "The external service is experiencing issues",
        "action": "Wait a moment and try again",
    },
    "rate_limited": {
        "patterns": ["rate limit", "too many requests", "429"],
        "category": FindingCategory.CONNECTION,
        "severity": FindingSeverity.WARNING,
        "title": "Rate limit exceeded",
        "detail": "Too many requests sent to the service",
        "action": "Wait a moment before retrying",
    },
    "not_found": {
        "patterns": ["not found", "404", "does not exist", "no results"],
        "category": FindingCategory.ERROR_PATTERN,
        "severity": FindingSeverity.INFO,
        "title": "Resource not found",
        "detail": "The requested resource could not be found",
        "action": "Verify the resource exists and try different search terms",
    },
    "permission_denied": {
        "patterns": ["permission denied", "forbidden", "403", "access denied", "not authorized"],
        "category": FindingCategory.CREDENTIALS,
        "severity": FindingSeverity.CRITICAL,
        "title": "Permission denied",
        "detail": "You don't have permission to access this resource",
        "action": "Check that your account has the required permissions",
    },
    "tool_unavailable": {
        "patterns": ["unknown tool", "tool not available", "tool not found", "tool failed to execute",
                      "not currently accessible", "no longer accessible", "functionality not accessible",
                      "connector unavailable", "connector needs to be"],
        "category": FindingCategory.MCP,
        "severity": FindingSeverity.CRITICAL,
        "title": "MCP tool not available",
        "detail": "A required tool is not registered or the MCP server is not running",
        "action": "Reconnect the datasource in Settings, or check that the MCP server is running",
    },
}


class ErrorInvestigationService:
    """
    Service for investigating errors detected in chat responses.

    Investigation order:
    1. Circuit breaker status - fastest check, indicates repeated failures
    2. Credential validation - do credentials exist? are tokens expired?
    3. MCP connection test - can we connect to the MCP server?
    4. Error pattern classification - what type of error is this?
    """

    def __init__(self):
        self._investigation_timeout = 10.0  # Max 10 seconds for investigation

    async def investigate(
        self,
        error_message: str,
        datasource: str,
        user_id: Optional[str],
        db: AsyncSession,
        session_id: Optional[str] = None,
    ) -> ErrorInvestigationResponse:
        """
        Investigate an error and return findings.

        Args:
            error_message: The error message from the chat response
            datasource: The datasource that caused the error
            user_id: Optional user ID for authenticated users
            db: Database session
            session_id: Optional session ID for anonymous users

        Returns:
            ErrorInvestigationResponse with findings and recommendations
        """
        start_time = time.time()
        investigation_id = str(uuid.uuid4())[:8]
        findings: List[InvestigationFinding] = []

        logger.info(f"[{investigation_id}] Starting error investigation for {datasource}")

        try:
            # Run investigation checks
            # 1. Check circuit breaker status (fastest)
            circuit_finding = await self._check_circuit_breaker(datasource)
            if circuit_finding:
                findings.append(circuit_finding)

            # 2. Check credentials
            cred_finding = await self._check_credentials(datasource, user_id, db, session_id)
            if cred_finding:
                findings.append(cred_finding)

            # 3. Check MCP connection (only if no critical findings yet)
            critical_findings = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
            if not critical_findings:
                mcp_finding = await self._check_mcp_connection(datasource, user_id, db, session_id)
                if mcp_finding:
                    findings.append(mcp_finding)

            # 4. Classify error pattern
            pattern_finding = self._classify_error_pattern(error_message)
            if pattern_finding:
                # Avoid duplicate findings for same issue
                existing_categories = {f.category for f in findings}
                if pattern_finding.category not in existing_categories:
                    findings.append(pattern_finding)

            # Determine root cause from highest severity finding
            root_cause = self._determine_root_cause(findings)

            # Generate recommendations
            recommendations = self._generate_recommendations(findings, datasource)

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"[{investigation_id}] Investigation completed in {duration_ms}ms. "
                f"Found {len(findings)} issues. Root cause: {root_cause}"
            )

            return ErrorInvestigationResponse(
                investigation_id=investigation_id,
                status="completed",
                root_cause=root_cause,
                findings=findings,
                recommendations=recommendations,
                investigated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"[{investigation_id}] Investigation timed out after {duration_ms}ms")
            return ErrorInvestigationResponse(
                investigation_id=investigation_id,
                status="timeout",
                root_cause="Investigation timed out",
                findings=findings,
                recommendations=["The investigation took too long. Please try again."],
                investigated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[{investigation_id}] Investigation failed: {e}")
            return ErrorInvestigationResponse(
                investigation_id=investigation_id,
                status="failed",
                root_cause=f"Investigation failed: {str(e)}",
                findings=findings,
                recommendations=["Unable to complete investigation. Please try again."],
                investigated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                duration_ms=duration_ms,
            )

    async def _check_circuit_breaker(self, datasource: str) -> Optional[InvestigationFinding]:
        """Check if the circuit breaker is open for this datasource."""
        try:
            breaker_name = f"mcp_{datasource}"
            breaker = mcp_circuit_breakers.get(breaker_name)

            if not breaker:
                return None

            stats = breaker.get_stats()
            state = breaker.state

            if state == CircuitState.OPEN:
                seconds_until_retry = stats.get("seconds_until_retry", 0)
                return InvestigationFinding(
                    category=FindingCategory.CIRCUIT_BREAKER,
                    severity=FindingSeverity.WARNING,
                    title=f"{datasource.title()} circuit breaker triggered",
                    detail=f"{stats.get('failure_count', 0)} consecutive failures detected. Auto-retry in {seconds_until_retry:.0f}s",
                    suggested_action=None,  # Auto-retry handles this
                )

            if state == CircuitState.HALF_OPEN:
                return InvestigationFinding(
                    category=FindingCategory.CIRCUIT_BREAKER,
                    severity=FindingSeverity.INFO,
                    title=f"{datasource.title()} service recovering",
                    detail="The service is being tested for recovery",
                    suggested_action=None,
                )

            # Circuit is closed but check failure count
            if stats.get("failure_count", 0) > 0:
                return InvestigationFinding(
                    category=FindingCategory.CIRCUIT_BREAKER,
                    severity=FindingSeverity.INFO,
                    title=f"{datasource.title()} experiencing intermittent issues",
                    detail=f"{stats.get('failure_count', 0)} recent failures, {stats.get('total_failures', 0)} total failures",
                    suggested_action=None,
                )

            return None

        except Exception as e:
            logger.warning(f"Error checking circuit breaker for {datasource}: {e}")
            return None

    async def _check_credentials(
        self,
        datasource: str,
        user_id: Optional[str],
        db: AsyncSession,
        session_id: Optional[str] = None,
    ) -> Optional[InvestigationFinding]:
        """Check if credentials exist and are valid for this datasource."""
        try:
            # Check if credentials exist
            has_creds = await credential_service.has_credentials(
                datasource=datasource,
                db=db,
                user_id=user_id,
                session_id=session_id,
            )

            if not has_creds:
                return InvestigationFinding(
                    category=FindingCategory.CREDENTIALS,
                    severity=FindingSeverity.CRITICAL,
                    title=f"No {datasource.title()} credentials found",
                    detail=f"You haven't connected your {datasource.title()} account yet",
                    suggested_action=f"Go to Settings > {datasource.title()} and click 'Connect'",
                )

            # Get credentials to check for expiration
            credentials = await credential_service.get_credentials(
                datasource=datasource,
                db=db,
                user_id=user_id,
                session_id=session_id,
            )

            if credentials:
                # Check if OAuth token is expired
                expires_at_str = credentials.get("expires_at")
                if expires_at_str:
                    try:
                        if expires_at_str.endswith("Z"):
                            expires_at_str = expires_at_str[:-1] + "+00:00"
                        expires_at = datetime.fromisoformat(expires_at_str)
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)

                        now = datetime.now(timezone.utc)
                        if expires_at < now:
                            hours_ago = int((now - expires_at).total_seconds() / 3600)
                            return InvestigationFinding(
                                category=FindingCategory.CREDENTIALS,
                                severity=FindingSeverity.CRITICAL,
                                title=f"{datasource.title()} authentication token has expired",
                                detail=f"Your OAuth token expired {hours_ago} hour{'s' if hours_ago != 1 else ''} ago",
                                suggested_action=f"Go to Settings > {datasource.title()} and click 'Reconnect'",
                            )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse expires_at: {e}")

                # Check OAuth type
                if credentials.get("oauth_type") == "user":
                    # Has OAuth credentials, check for refresh token
                    refresh_token_key = f"{datasource.lower()}_refresh_token"
                    if datasource.lower() == "google_workspace":
                        refresh_token_key = "google_refresh_token"
                    elif datasource.lower() == "jira":
                        refresh_token_key = "jira_refresh_token"

                    if not credentials.get(refresh_token_key):
                        return InvestigationFinding(
                            category=FindingCategory.CREDENTIALS,
                            severity=FindingSeverity.WARNING,
                            title=f"{datasource.title()} missing refresh token",
                            detail="Unable to automatically refresh your access token",
                            suggested_action=f"Go to Settings > {datasource.title()} and reconnect your account",
                        )

            return None

        except Exception as e:
            logger.warning(f"Error checking credentials for {datasource}: {e}")
            return None

    async def _check_mcp_connection(
        self,
        datasource: str,
        user_id: Optional[str],
        db: AsyncSession,
        session_id: Optional[str] = None,
    ) -> Optional[InvestigationFinding]:
        """Check if we can connect to the MCP server."""
        try:
            result = await asyncio.wait_for(
                mcp_service.test_connection(
                    datasource=datasource,
                    user_id=user_id,
                    session_id=session_id,
                    db=db,
                ),
                timeout=5.0,
            )

            if not result.get("connected"):
                error_msg = result.get("message", "Unknown error")
                return InvestigationFinding(
                    category=FindingCategory.MCP,
                    severity=FindingSeverity.CRITICAL,
                    title=f"Cannot connect to {datasource.title()} service",
                    detail=f"Connection test failed: {error_msg}",
                    suggested_action="Check your credentials and network connection",
                )

            return None

        except asyncio.TimeoutError:
            return InvestigationFinding(
                category=FindingCategory.MCP,
                severity=FindingSeverity.WARNING,
                title=f"{datasource.title()} connection timeout",
                detail="The connection test took too long to complete",
                suggested_action="The service may be slow. Try again in a moment.",
            )
        except Exception as e:
            return InvestigationFinding(
                category=FindingCategory.MCP,
                severity=FindingSeverity.WARNING,
                title=f"{datasource.title()} connection check failed",
                detail=str(e),
                suggested_action="Try again or check your settings",
            )

    def _classify_error_pattern(self, error_message: str) -> Optional[InvestigationFinding]:
        """Classify the error message based on known patterns."""
        error_lower = error_message.lower()

        for pattern_name, pattern_config in ERROR_PATTERNS.items():
            for pattern in pattern_config["patterns"]:
                if pattern in error_lower:
                    return InvestigationFinding(
                        category=pattern_config["category"],
                        severity=pattern_config["severity"],
                        title=pattern_config["title"],
                        detail=pattern_config["detail"],
                        suggested_action=pattern_config["action"],
                    )

        return None

    def _determine_root_cause(self, findings: List[InvestigationFinding]) -> Optional[str]:
        """Determine the root cause from findings."""
        if not findings:
            return "Unable to determine root cause"

        # Sort by severity (critical first)
        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.INFO: 2,
        }
        sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.severity, 3))

        # Return the title of the highest severity finding
        return sorted_findings[0].title

    def _generate_recommendations(
        self,
        findings: List[InvestigationFinding],
        datasource: str,
    ) -> List[str]:
        """Generate recommendations based on findings."""
        recommendations = []

        for finding in findings:
            if finding.suggested_action:
                recommendations.append(finding.suggested_action)

        # Add general recommendations if needed
        if not recommendations:
            recommendations.append("Try your request again")
            recommendations.append(f"Check your {datasource.title()} connection in Settings")

        # Deduplicate while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)

        return unique_recommendations


    async def remediate(
        self,
        datasource: str,
        user_id: Optional[str],
        db: AsyncSession,
        session_id: Optional[str] = None,
        findings: Optional[List[InvestigationFinding]] = None,
    ) -> "RemediationResponse":
        """
        Attempt to automatically fix issues found during investigation.

        Remediation steps (in order):
        1. Reset circuit breaker if open
        2. Refresh OAuth token if expired
        3. Clear stale tools cache
        4. Test MCP connection to verify fix

        Returns a RemediationResponse with what was attempted and whether it worked.
        """
        start_time = time.time()
        actions_taken: List[RemediationAction] = []

        logger.info(f"Starting auto-remediation for {datasource}")

        # 1. Reset circuit breaker
        try:
            breaker_name = f"mcp_{datasource}"
            breaker = mcp_circuit_breakers.get(breaker_name)
            if breaker and breaker.state != CircuitState.CLOSED:
                mcp_circuit_breakers.reset(breaker_name)
                actions_taken.append(RemediationAction(
                    action="reset_circuit_breaker",
                    success=True,
                    detail=f"Reset circuit breaker for {datasource}",
                ))
                logger.info(f"Reset circuit breaker for {datasource}")
        except Exception as e:
            actions_taken.append(RemediationAction(
                action="reset_circuit_breaker",
                success=False,
                detail=f"Failed to reset circuit breaker: {e}",
            ))

        # 2. Refresh OAuth token
        try:
            from app.services.user_oauth_service import user_oauth_service

            if user_id and db:
                credentials = await credential_service.get_credentials(
                    datasource=datasource, db=db, user_id=user_id,
                )
                if credentials and credentials.get("oauth_type") == "user":
                    refreshed = await mcp_service._try_refresh_oauth_token(
                        datasource, user_id, db,
                    )
                    if refreshed:
                        actions_taken.append(RemediationAction(
                            action="refresh_oauth_token",
                            success=True,
                            detail=f"Successfully refreshed OAuth token for {datasource}",
                        ))
                        logger.info(f"Refreshed OAuth token for {datasource}")
                    else:
                        actions_taken.append(RemediationAction(
                            action="refresh_oauth_token",
                            success=False,
                            detail=f"Could not refresh token — may need manual reconnection",
                        ))
                else:
                    actions_taken.append(RemediationAction(
                        action="refresh_oauth_token",
                        success=False,
                        detail="No OAuth credentials found to refresh",
                    ))
        except Exception as e:
            actions_taken.append(RemediationAction(
                action="refresh_oauth_token",
                success=False,
                detail=f"Token refresh failed: {e}",
            ))

        # 3. Clear stale tools cache
        try:
            from app.services.mcp_service import TOOLS_CACHE, TOOLS_CACHE_LOCK
            async with TOOLS_CACHE_LOCK:
                if datasource in TOOLS_CACHE:
                    del TOOLS_CACHE[datasource]
                    actions_taken.append(RemediationAction(
                        action="clear_tools_cache",
                        success=True,
                        detail=f"Cleared stale tools cache for {datasource}",
                    ))
                    logger.info(f"Cleared tools cache for {datasource}")
                else:
                    actions_taken.append(RemediationAction(
                        action="clear_tools_cache",
                        success=True,
                        detail="Tools cache was already empty",
                    ))
        except Exception as e:
            actions_taken.append(RemediationAction(
                action="clear_tools_cache",
                success=False,
                detail=f"Failed to clear cache: {e}",
            ))

        # 4. Test connection to verify fix
        connection_ok = False
        try:
            result = await asyncio.wait_for(
                mcp_service.test_connection(
                    datasource=datasource,
                    user_id=user_id,
                    session_id=session_id,
                    db=db,
                ),
                timeout=10.0,
            )
            connection_ok = result.get("connected", False)
            actions_taken.append(RemediationAction(
                action="test_connection",
                success=connection_ok,
                detail=result.get("message", "Connection test completed"),
            ))
        except asyncio.TimeoutError:
            actions_taken.append(RemediationAction(
                action="test_connection",
                success=False,
                detail="Connection test timed out",
            ))
        except Exception as e:
            actions_taken.append(RemediationAction(
                action="test_connection",
                success=False,
                detail=f"Connection test failed: {e}",
            ))

        duration_ms = int((time.time() - start_time) * 1000)
        all_succeeded = all(a.success for a in actions_taken)
        any_succeeded = any(a.success for a in actions_taken)

        if connection_ok:
            status = "fixed"
            message = f"{datasource.title()} connection restored. Please retry your query."
        elif any_succeeded:
            status = "partial"
            message = f"Some fixes applied but {datasource.title()} connection could not be verified. You may need to reconnect in Settings."
        else:
            status = "failed"
            message = f"Auto-fix failed. Please reconnect {datasource.title()} in Settings."

        logger.info(
            f"Remediation for {datasource}: status={status}, "
            f"actions={len(actions_taken)}, duration={duration_ms}ms"
        )

        return RemediationResponse(
            status=status,
            message=message,
            actions=actions_taken,
            connection_restored=connection_ok,
            duration_ms=duration_ms,
        )


@dataclass
class RemediationAction:
    """A single remediation action taken."""
    action: str
    success: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "success": self.success,
            "detail": self.detail,
        }


@dataclass
class RemediationResponse:
    """Response from a remediation attempt."""
    status: str  # 'fixed', 'partial', 'failed'
    message: str
    actions: List[RemediationAction]
    connection_restored: bool
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "actions": [a.to_dict() for a in self.actions],
            "connection_restored": self.connection_restored,
            "duration_ms": self.duration_ms,
        }


# Singleton instance
error_investigation_service = ErrorInvestigationService()

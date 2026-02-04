# ConnectorMCP Incident Response Guide

## Severity Definitions

### P0 - Critical
**Impact:** Complete service outage or security breach
**Response Time:** Immediate (< 15 minutes)
**Examples:**
- All users unable to access the service
- Data breach or unauthorized access detected
- Database completely unavailable
- Authentication system compromised

### P1 - High
**Impact:** Major feature unavailable or significant degradation
**Response Time:** < 1 hour
**Examples:**
- All MCP connectors failing
- OAuth flows completely broken
- > 50% of requests failing
- Response times > 10x normal

### P2 - Medium
**Impact:** Partial feature degradation, workarounds available
**Response Time:** < 4 hours
**Examples:**
- Single datasource connector failing
- Rate limiting incorrectly blocking users
- Slow performance (< 5x normal)
- Non-critical API errors

### P3 - Low
**Impact:** Minor issues, no significant user impact
**Response Time:** Next business day
**Examples:**
- Cosmetic issues
- Non-critical logging errors
- Documentation inaccuracies
- Minor performance improvements needed

## Escalation Paths

### On-Call Rotation
```
L1: SRE On-Call
    └─→ L2: Senior SRE / Tech Lead
        └─→ L3: Engineering Manager
            └─→ L4: VP Engineering / CTO
```

### Escalation Criteria
- **P0:** Immediately escalate to L2
- **P1:** Escalate to L2 if not resolved within 30 minutes
- **P2:** Escalate to L2 if not resolved within 2 hours
- **P3:** Handle during business hours, escalate if blocked

### Contact Information
| Role | Primary Contact | Backup Contact |
|------|----------------|----------------|
| SRE On-Call | PagerDuty | Slack #oncall |
| Tech Lead | Direct page | Email |
| Eng Manager | Phone | Slack DM |

## Incident Response Workflow

### 1. Detection & Triage (0-15 minutes)
- [ ] Acknowledge alert in PagerDuty
- [ ] Join incident Slack channel: #incidents
- [ ] Assess severity using definitions above
- [ ] Assign Incident Commander (IC)

### 2. Initial Response (15-30 minutes)
- [ ] IC creates incident ticket
- [ ] Gather initial information:
  - What is the impact?
  - When did it start?
  - What changed recently?
- [ ] Start incident timeline documentation
- [ ] Communicate initial status to stakeholders

### 3. Investigation (30+ minutes)
- [ ] Check dashboards and metrics
- [ ] Review recent deployments
- [ ] Check external dependencies
- [ ] Collect relevant logs
- [ ] Form hypothesis and test

### 4. Mitigation
- [ ] Implement fix or workaround
- [ ] Verify fix is working
- [ ] Monitor for recurrence
- [ ] Update stakeholders

### 5. Resolution
- [ ] Confirm service is fully restored
- [ ] Send resolution communication
- [ ] Schedule post-incident review

## Communication Templates

### Initial Notification
```
Subject: [P{SEVERITY}] {SERVICE} - {BRIEF DESCRIPTION}

Status: Investigating
Impact: {USER IMPACT}
Start Time: {TIMESTAMP}

We are aware of an issue affecting {SERVICE} and are actively investigating.

Current impact: {DESCRIPTION OF USER EXPERIENCE}

Next update in: 30 minutes
```

### Update Template
```
Subject: [P{SEVERITY}] {SERVICE} - UPDATE #{N}

Status: {Investigating | Identified | Monitoring | Resolved}
Impact: {USER IMPACT}
Duration: {TIME SINCE START}

Update:
{WHAT WE KNOW NOW}

Actions taken:
- {ACTION 1}
- {ACTION 2}

Next steps:
- {NEXT STEP}

Next update in: {TIME}
```

### Resolution Template
```
Subject: [RESOLVED] {SERVICE} - {BRIEF DESCRIPTION}

Status: Resolved
Duration: {TOTAL DURATION}
Impact: {FINAL IMPACT SUMMARY}

Summary:
{BRIEF DESCRIPTION OF WHAT HAPPENED}

Root Cause:
{ROOT CAUSE IF KNOWN}

Resolution:
{WHAT FIXED IT}

Follow-up:
- Post-incident review scheduled for: {DATE}
- Tracking ticket: {LINK}
```

## Post-Incident Review Process

### When to Conduct
- All P0 and P1 incidents
- P2 incidents lasting > 4 hours
- Any incident with customer-visible impact
- Any incident revealing systemic issues

### Review Timeline
- Schedule within 3 business days
- Complete review document within 5 business days
- Action items assigned and tracked

### Review Template

#### Incident Summary
- **Date/Time:**
- **Duration:**
- **Severity:**
- **Impact:**

#### Timeline
| Time | Event |
|------|-------|
| HH:MM | Initial alert |
| HH:MM | IC assigned |
| HH:MM | Root cause identified |
| HH:MM | Fix deployed |
| HH:MM | Service restored |

#### Root Cause Analysis
**What happened:**

**Why it happened:**
1. Why? →
2. Why? →
3. Why? →
4. Why? →
5. Why? → (Root cause)

#### What Went Well
-

#### What Could Be Improved
-

#### Action Items
| Item | Owner | Due Date | Status |
|------|-------|----------|--------|
| | | | |

### Blameless Culture
- Focus on systems, not individuals
- Assume everyone acted with best intentions
- Identify process improvements
- Share learnings openly

## Runbooks Quick Reference

### Service Restart
```bash
# Rolling restart (preferred)
kubectl rollout restart deployment/connectormcp-backend

# Check rollout status
kubectl rollout status deployment/connectormcp-backend
```

### Database Quick Checks
```bash
# Check connectivity
mysql -h $DB_HOST -u $DB_USER -p -e "SELECT 1"

# Check active connections
mysql -e "SHOW STATUS LIKE 'Threads_connected'"
```

### Log Search
```bash
# Recent errors
grep -i error /var/log/connectormcp/app.log | tail -50

# Specific user issues
grep "user_id\":\"$USER_ID" /var/log/connectormcp/app.log
```

### Circuit Breaker Reset
```bash
# Restart specific backend instance to reset circuit breakers
kubectl delete pod $POD_NAME
```

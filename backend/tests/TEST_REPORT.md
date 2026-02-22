# ConnectorMCP Test Report

**Generated:** 2025-12-16T19:40:43.732302

## Summary

| Metric | Count |
|--------|-------|
| Total Tests | 25 |
| Passed | 22 |
| Failed | 1 |
| Warnings | 2 |
| **Pass Rate** | **88.0%** |

## Discovered Data

### Slack Users

- Slackbot
- Krishnan Naranapatty
- CEO
- Senior DevOps Engineer
- Allan David
- lakshmi Gajendran
- Bharath Jeeva
- Product Manager
- Guptha Kalva
- Senior Software Test Engineer
- Lavanya Deenadayalan
- Mohanraj Rajendran
- Vivek Sundararaman
- Chandru
- Muthamil Selvan

### JIRA Projects

- JIRA
- GTMS
- TGSOLD
- MDP
- DUW
- ORAI
- ORALIA
- JMT

### JIRA Assignees

- To Do
- Austin Prabu
- Query Results

## Failed Tests

### Empty query (should fail gracefully)
- **Query:**    
- **Duration:** 11ms
- **Issues:**
  - Error: HTTP 400


## Warnings

### Slack: Non-existent person
- **Query:** What is Zyxwvutsrq Mcfakename working on?
  - Missing expected term: 'not found'

### JIRA: Non-existent person
- **Query:** What is Fakeperson Notreal working on?
  - Expected error message but got normal response
  - Missing expected term: 'not found'


## All Tests

| Status | Test | Duration | Issues |
|--------|------|----------|--------|
| ✓ PASSED | Slack: Activity for Slackbot | 10866ms | - |
| ✓ PASSED | Slack: Activity for Krishnan | 9857ms | - |
| ✓ PASSED | Slack: Activity for CEO | 5646ms | Missing Sources section |
| ✓ PASSED | Slack: Activity for Senior | 6247ms | Missing Sources section |
| ✓ PASSED | Slack: Activity for Allan | 10500ms | - |
| ✓ PASSED | Slack: DM with Slackbot | 12070ms | - |
| ⚠ WARNING | Slack: Non-existent person | 7281ms | Missing expected term: 'not found' |
| ✓ PASSED | Slack: List channels | 23440ms | - |
| ✓ PASSED | Slack: Read general | 15989ms | - |
| ✓ PASSED | Slack: Search keyword | 14344ms | - |
| ✓ PASSED | JIRA: Work for To | 7670ms | Missing Sources section |
| ✓ PASSED | JIRA: Work for Austin | 7064ms | Missing Sources section |
| ✓ PASSED | JIRA: Work for Query | 7203ms | Missing Sources section |
| ⚠ WARNING | JIRA: Non-existent person | 8377ms | Expected error message but got normal response; Missing expected term: 'not found' |
| ✓ PASSED | JIRA: Issues in JIRA | 10727ms | - |
| ✓ PASSED | JIRA: Issues in GTMS | 8788ms | Missing Sources section |
| ✓ PASSED | JIRA: Behind schedule | 14466ms | - |
| ✓ PASSED | JIRA: Overdue issues | 9433ms | - |
| ✓ PASSED | JIRA: Blocked issues | 10378ms | - |
| ✓ PASSED | JIRA: Bug count | 11123ms | - |
| ✓ PASSED | JIRA: In review | 7397ms | - |
| ✗ FAILED | Empty query (should fail gracefully) | 11ms | Error: HTTP 400 |
| ✓ PASSED | Unicode in name | 6738ms | - |
| ✓ PASSED | Special chars in query | 9137ms | - |
| ✓ PASSED | Slack: Ambiguous name (John) | 6793ms | - |
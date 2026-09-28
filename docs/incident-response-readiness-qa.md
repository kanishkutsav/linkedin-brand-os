# Incident Response Readiness — QA

## Detection
Security events currently log:
- CSRF validation failures
- rate-limit events
- request correlation IDs
- authenticated application actions through the existing audit trail where applicable

Do not log session tokens, LinkedIn access tokens, provider API keys, or full user prompts.

## Immediate response
1. Preserve relevant application, hosting, database and provider logs.
2. Identify affected accounts, sessions, data objects and external integrations.
3. Revoke affected Suvacya sessions.
4. Disconnect/revoke affected LinkedIn credentials where supported.
5. Rotate the affected encryption/API secrets.
6. Contain the affected endpoint, deployment or integration.
7. Preserve forensic evidence before destructive cleanup.
8. Record a timeline, scope, root cause, corrective actions and user impact.

## India/CERT-In readiness
CERT-In's published 28 April 2022 directions state that covered organisations must maintain ICT-system logs securely for a rolling 180 days and report covered cyber incidents within six hours of noticing them. The production implementation must confirm applicability, designate the required point of contact, select the compliant log-retention location, and establish the actual reporting workflow before launch.

## Data-subject response
The product exposes account export and account deletion controls. Deletion should be blocked or partially retained only where retention is necessary for an applicable legal/security obligation, with the retained category and reason documented.

## Exercises
Before production:
- run an OAuth replay exercise
- run a session theft/revocation exercise
- run cross-user authorization tests
- run deletion/export verification
- run provider-key rotation
- run backup/restore validation
- run a tabletop incident exercise

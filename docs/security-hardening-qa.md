# QA security hardening

This document records the controls implemented in the QA branch for the security/privacy audit.

## Runtime controls

- Browser authentication uses an HttpOnly, Secure, SameSite=Lax session cookie in production.
- Browser API calls use a CSRF cookie-to-header control for unsafe methods.
- Legacy bearer authentication remains accepted for non-browser integrations and automated jobs; the web UI no longer persists bearer tokens.
- LinkedIn OAuth browser nonces are stored as hashes in the server-side OAuth transaction and checked again during one-time exchange.
- LinkedIn access tokens are encrypted before persistence. Key material is supplied through environment configuration and supports key rotation by ordered key list.
- Security-sensitive endpoints have endpoint-specific request throttling.
- API responses receive baseline security headers, including CSP, HSTS in production, Referrer-Policy, Permissions-Policy and nosniff.
- AI prompts pass through a PII/credential minimization layer before being sent to configured providers.
- Direct Supabase Data API access to application tables is denied to anon/authenticated roles; the application server remains the authorization boundary.

## Operational controls

CERT-In's published directions state that covered organisations must maintain ICT-system logs securely for a rolling 180 days and report covered cyber incidents within six hours of noticing them. Applicability to this product and the required retention location should be confirmed with counsel/compliance before production launch.

## Remaining external confirmations

- Privacy Policy, Terms and processor/DPA language require legal review.
- AI-provider retention/training/region/DPA terms must be verified against the exact accounts and plans used.
- LinkedIn product/API permissions and contractual eligibility must be confirmed with LinkedIn.
- Production secrets must be provisioned through the deployment secret manager; never commit them to the repository.

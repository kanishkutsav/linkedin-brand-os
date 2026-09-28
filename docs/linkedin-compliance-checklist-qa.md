# LinkedIn integration compliance checklist — QA

The implementation uses LinkedIn's official OAuth and API endpoints and keeps external publishing behind the product's human approval workflow.

Before production launch, verify against LinkedIn's then-current documentation and the application's actual developer-program approvals:

- exact OAuth scopes provisioned to the application
- OIDC/profile fields available to the application
- Share on LinkedIn / publishing product eligibility
- analytics permissions, if enabled
- redirect URI registration
- rate limits and product-specific quotas
- data-use and storage restrictions
- deletion/disconnection obligations
- any review, approval or contractual requirements attached to the product

The repository must not treat technical implementation as proof of contractual eligibility.

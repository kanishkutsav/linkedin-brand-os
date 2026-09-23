# Architecture v0.1

## Hard boundary
Only `ActionExecutor` may invoke an external LinkedIn adapter. It requires a non-expired approval, exact content hash match, policy pass, integration capability, and emergency-stop disabled.

## Services
- Strategy: positioning, pillars, calendar
- Research: sources/evidence packs
- Content: ideas/drafts/replies
- Engagement: opportunities/comments
- Analytics: metrics/experiments
- Memory: profile, voice, content, feedback
- Guards: identity, claims, brand, duplicates, privacy, sensitive topics, rate limits
- Approval: HITL state machine
- Action Executor: only external-action boundary

## MVP integration
LinkedIn is represented by a mock adapter. Replace only the adapter after validating the developer application's current officially supported permissions and products.

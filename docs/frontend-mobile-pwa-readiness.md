# Frontend Mobile & PWA Readiness — Engineering Checkpoint

## Production baseline

- Repository: `kanishkutsav/linkedin-brand-os`
- Production branch: `master`
- Baseline commit reviewed: `4b854980555e4836fbda73214096c3f3ee61f4c5`
- Frontend: Next.js App Router, React client workspace, CSS in `apps/web/app/globals.css`
- No backend/API/database changes are in scope for this work.

## Frontend inventory reviewed

- `/`: authenticated workspace shell and login screen
- Workspace modules: Dashboard, Research, Content Studio, LinkedIn Posts, Analytics, Brand DNA, Jobs, Feedback, Admin
- `/admin`: redirect entry into the workspace
- `/privacy` and `/terms`: legal pages
- Shared Jobs module: `apps/web/components/jobs-view.tsx`
- Admin operations and Account Directory are embedded in the workspace page.
- PWA files: `layout.tsx`, `manifest.webmanifest`, `sw.js`, public icons and install UI.
- Build/security configuration: `next.config.mjs`, package scripts, and GitHub Actions workflow.

## Production code paths inspected

- `apps/web/app/page.tsx` (workspace state, auth bootstrap, API fetch wrapper, tab routing, install prompt, mobile navigation, module renderers)
- `apps/web/app/globals.css` (design tokens, component styling, responsive breakpoints and mobile shell)
- `apps/web/app/layout.tsx`
- `apps/web/components/jobs-view.tsx`
- `apps/web/app/admin/page.tsx`
- `apps/web/app/privacy/page.tsx`
- `apps/web/app/terms/page.tsx`
- `apps/web/next.config.mjs`
- `apps/web/package.json`
- `apps/web/public/manifest.webmanifest`
- `apps/web/public/sw.js`
- `.github/workflows/phase2-qa.yml`

## Identified mobile/PWA concerns

- Responsive styles existed but had accumulated multiple overlapping breakpoints and module-specific overrides.
- Touch sizing, iOS input zoom prevention, narrow-width overflow and safe-area handling needed consistent final overrides.
- PWA manifest already existed; its theme/background colours did not match the current navy product shell.
- Existing service worker cached navigation responses. This could persist personalized authenticated HTML in a shared browser cache.
- The Research PWA shortcut used a lowercase tab value although workspace tab matching is case-sensitive.
- PWA was forcing portrait orientation despite tablet/landscape use being part of the target.

## Changes in PR #111

- Additive mobile CSS overrides for workspace modules, navigation, controls, forms, Admin, Jobs, legal pages, dialogs and safe areas.
- Touch targets and mobile input font sizing improved.
- Mobile admin count/filter controls and navigation are constrained to the viewport.
- Service worker now uses network-only navigation for app pages; authenticated HTML, API and OAuth traffic are never cached.
- Offline navigation falls back to a static, non-personalized `offline.html`.
- Only Next.js immutable static assets and public icons are cacheable.
- Manifest has a stable `id`, matching brand theme/background colours, a raster icon fallback, corrected shortcuts and unrestricted orientation.
- CI validates service-worker syntax, manifest essentials, icon references and offline fallback presence.

## Safety boundaries

- No API contracts, authentication flow, backend code, database schema, schedulers, LinkedIn publishing, content workflows or account controls were changed.
- Do not add caching for `/api/*`, OAuth, authenticated navigations or user-specific responses.
- Avoid broad refactors of the large workspace component in this mobile-readiness pass.
- Production changes must remain behind PR review and passing CI.

## Verification status

- Static code review completed for the frontend inventory above.
- GitHub Actions is running frontend build, dependency audit and existing backend/regression suites.
- PWA-specific static validation was added to frontend CI.
- Real-device visual QA (Android Chrome installed mode, iOS Safari Home Screen mode, tablet landscape and small-width screens) remains a manual verification item; CI build alone cannot prove visual rendering or browser install UX.

## Resume protocol

1. Read this checkpoint before continuing.
2. Re-fetch the current PR head and GitHub Actions run status; do not assume the branch SHA or CI status from an earlier message.
3. Inspect failed job logs and fix only the failing area.
4. Do not merge until the latest PR head has green required checks.
5. After merge, verify the Vercel production deployment is READY and points at the merge commit.
6. Re-check the production manifest, offline fallback and service-worker response policy after deployment.

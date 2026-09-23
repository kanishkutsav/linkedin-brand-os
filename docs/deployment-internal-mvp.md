# Internal MVP deployment foundation

## Target stack
- Frontend: Vercel + Next.js
- API: Render + FastAPI
- Database: Supabase Postgres
- Auth: Supabase Auth
- Safe execution: backend-only approval gate

## Core principles
1. AI prepares content and recommendations.
2. Human reviews and approves inside the dashboard.
3. Only approved actions execute through the backend adapter.
4. All actions are logged and auditable.
5. No browser-side execution of external APIs.

## Production setup
### Vercel
- Deploy the Next.js app from apps/web
- Add environment variables:
  - NEXT_PUBLIC_API_URL
  - NEXT_PUBLIC_APP_ENV
  - NEXT_PUBLIC_SUPABASE_URL
  - NEXT_PUBLIC_SUPABASE_ANON_KEY

### Render
- Deploy the FastAPI app from apps/api
- Set environment variables:
  - DATABASE_URL
  - SECRET_KEY
  - APP_ENV=production
  - CORS_ORIGINS
  - SUPABASE_URL
  - SUPABASE_ANON_KEY
  - LINKEDIN_CLIENT_ID
  - LINKEDIN_CLIENT_SECRET
  - LINKEDIN_API_BASE_URL

### Supabase
- Create a Postgres project
- Use the SQLAlchemy schema from the app models as the source of truth
- For local dev, SQLite remains acceptable
- For internal MVP deployment, prefer Postgres everywhere

## Required operational safeguards
- Approval TTL enforcement
- Audit log persistence
- Content hash verification
- Emergency stop handling
- Permission checks for approval actions
- Health check endpoint for Render

## Known constraint
The LinkedIn execution layer remains intentionally narrow and policy-compliant. It should not be enabled for production until the exact platform permissions and compliance posture are validated.

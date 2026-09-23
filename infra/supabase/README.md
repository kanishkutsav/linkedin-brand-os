# Supabase deployment setup

1. Create a Supabase project.
2. Open the SQL editor.
3. Run the SQL from infra/supabase/schema.sql.
4. Copy the Postgres connection string into Render and app env configuration.
5. Keep the application DATABASE_URL set to the Supabase Postgres URL in production.
6. Add the Supabase URL and anon/service role keys to the API environment.
7. Set the frontend Vercel environment variable NEXT_PUBLIC_API_URL to the deployed Render API URL.

Recommended production connection string format:

postgresql+asyncpg://postgres:your-password@host:5432/postgres

Required Render environment variables:
- APP_ENV=production
- ENVIRONMENT=production
- DATABASE_URL=postgresql+asyncpg://postgres:...@...:5432/postgres
- SECRET_KEY=your-long-random-secret
- JWT_SECRET=your-long-random-secret
- CORS_ORIGINS=https://your-vercel-domain.vercel.app
- FRONTEND_URL=https://your-vercel-domain.vercel.app
- SUPABASE_URL=https://your-project.supabase.co
- SUPABASE_ANON_KEY=...
- SUPABASE_SERVICE_ROLE_KEY=...

Required Vercel environment variables:
- NEXT_PUBLIC_API_URL=https://your-render-service.onrender.com
- NEXT_PUBLIC_APP_ENV=production

This is the durable data store for:
- user profile and voice memory
- user auth records and issued sessions
- drafts and content versions
- approval requests and feedback history
- audit logs and emergency stop state

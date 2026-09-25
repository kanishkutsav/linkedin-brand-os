# LinkedIn Personal Brand OS

HITL-first AI personal-brand manager. AI prepares; human decides; approved actions execute only through a compliant integration.

## Current status
This repository is a strong internal MVP foundation for a human-in-the-loop personal brand workflow. It is intentionally designed around safety, approval gating, and a narrow execution boundary.

## Python runtime
The API is intentionally aligned to **CPython 3.14.7**. The dependency set uses current FastAPI/Pydantic/SQLAlchemy/Uvicorn releases that publish Python 3.14 support/wheels where applicable.

## MVP
- Brand/profile + voice configuration
- Content ideas and drafts
- Guardrail checks
- Approval queue with content-hash-bound approvals
- Audit log
- Pluggable LinkedIn adapter (mock by default)
- Next.js dashboard shell

## Safety boundary
No agent has direct access to external LinkedIn actions. Only the Action Executor may call an integration, and it requires a valid approval token, matching content hash, policy approval, and an enabled integration.

## Internal MVP production foundation
This branch is meant to be a deployable internal MVP foundation for Vercel + Render + Supabase. It keeps the product safe and review-driven while preparing the app for real deployment structure.

### Production target architecture
- Frontend: Next.js on Vercel
- API: FastAPI on Render
- Database: Supabase Postgres
- Auth: Supabase Auth
- Execution layer: strict approval-gated adapter

## Run API with Python 3.14.7

### Windows PowerShell
```powershell
cd apps/api
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

### macOS / Linux
```bash
cd apps/api
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

API health: `http://localhost:8000/health`
API docs: `http://localhost:8000/docs`

## Run web
```bash
cd apps/web
npm install
npm run dev
```

## Production environment checklist
Required deployment values:
- DATABASE_URL (Supabase Postgres connection string)
- SECRET_KEY
- APP_ENV=production
- CORS_ORIGINS
- SUPABASE_URL
- SUPABASE_ANON_KEY
- LINKEDIN_CLIENT_ID
- LINKEDIN_CLIENT_SECRET
- LINKEDIN_API_BASE_URL

The default LinkedIn adapter is a mock. Real LinkedIn OAuth/API integration is intentionally not enabled until the exact permissions and approved capabilities for the developer application are validated.

## Deployment plan
- Web UI: Vercel
- API: Render
- Database: Supabase Postgres
- Approval workflow and audit state: Postgres-backed tables
- Safe execution boundary: backend-only, never browser-executable


<!-- deployment sync -->

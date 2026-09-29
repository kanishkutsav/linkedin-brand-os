import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request, File, UploadFile, Header
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, inspect, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.research import ResearchService
from app.agents.orchestrator import AgentOrchestrator
from app.agents.strategy import ContentStrategyService
from app.agents.voice import VoiceProfileBuilder
from app.auth import require_roles
from app.core.config import settings
from app.db.database import engine, get_session, SessionLocal
from app.services.agent_scheduler import AgentScheduler
from app.jobs.scheduled_jobs import ScheduledJobs
from app.jobs.durable_queue import enqueue_job
from app.services.brand_intelligence import BrandIntelligenceService
from app.services.brand_learning import BrandLearningService
from app.guards.guardrails import normalize_human_style, run_content_guards
from app.integrations.linkedin import OfficialLinkedInAdapter
from app.models.base import Base
from app.models.models import (
    ApprovalRequest, AuditLog, AuthSession, AuthUser, AgentRun, BrandMemory, ContentItem,
    ContentOpportunity, ContentVersion, DurableJob, FeedbackEntry, HistoricalPost,
    LearningEvent, LearningMemory, LinkedInConnection, LinkedInOAuthExchange, LinkedInOAuthState,
    ResearchSource, UserProfile, VoiceMemory, ObservabilityEvent, UserFeedback, JobSearchCache,
)
from app.services.approval import ApprovalService
from app.services.auth_service import AppUser, AuthService
from app.services.linkedin_oauth import build_authorization_url, exchange_code, handle_callback, sync_missing_profile_data
from app.services.linkedin_analytics import LinkedInAnalyticsService
from app.services.gemini_service import ModelRouterService
from app.services.jobs import resolve_job_location, search_jobs
from app.services.security import (
    CSRF_COOKIE, SESSION_COOKIE, clear_session_cookies, client_key, decrypt_linkedin_token, encrypt_linkedin_token,
    endpoint_limit, migrate_plaintext_linkedin_tokens, rate_limiter, request_token,
    security_event, set_session_cookies, validate_csrf_token,
)

logger = logging.getLogger(__name__)


def _resolve_sqlite_path() -> str | None:
    database_url = settings.database_url
    if not database_url.startswith("sqlite"):
        return None

    normalized = database_url.replace("sqlite+aiosqlite:///", "", 1).replace("sqlite:///", "", 1)
    normalized = normalized.replace("sqlite://", "", 1)
    if not normalized:
        return None
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith(".\\"):
        normalized = normalized[2:]
    return os.path.abspath(normalized)


def _database_needs_reset() -> bool:
    absolute_path = _resolve_sqlite_path()
    if absolute_path is None or not os.path.exists(absolute_path):
        return False

    required_tables = {
        "user_profiles",
        "voice_memory",
        "content_items",
        "content_versions",
        "approval_requests",
        "feedback_entries",
        "audit_logs",
        "system_flags",
    }

    try:
        with sqlite3.connect(absolute_path) as conn:
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            return not required_tables.issubset(existing)
    except sqlite3.Error:
        return False


agent_scheduler = AgentScheduler(SessionLocal)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Vercel uses the already-migrated Supabase schema. Avoid per-invocation
    # DDL and local SQLite file work in ephemeral functions.
    vercel_runtime = os.getenv("VERCEL", "").lower() == "1"
    if not vercel_runtime:
        absolute_path = _resolve_sqlite_path()
        if _database_needs_reset() and absolute_path and os.path.exists(absolute_path):
            os.remove(absolute_path)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            columns = await conn.run_sync(lambda sync_conn: {
                column["name"] for column in inspect(sync_conn).get_columns("user_profiles")
            })
            if "experience_years" not in columns:
                await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN experience_years FLOAT"))
            if "brand_bootstrap_completed" not in columns:
                await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN brand_bootstrap_completed BOOLEAN NOT NULL DEFAULT FALSE"))

            linkedin_columns = await conn.run_sync(lambda sync_conn: {
                column["name"] for column in inspect(sync_conn).get_columns("linkedin_connections")
            })
            linkedin_column_sql = {
                "linkedin_headline": "TEXT",
                "linkedin_picture_url": "TEXT",
                "linkedin_locale": "VARCHAR(30)",
                "linkedin_vanity_name": "VARCHAR(255)",
                "linkedin_profile_synced_at": "TIMESTAMP",
            }
            for column_name, column_type in linkedin_column_sql.items():
                if column_name not in linkedin_columns:
                    await conn.execute(text(f"ALTER TABLE linkedin_connections ADD COLUMN {column_name} {column_type}"))

            approval_columns = await conn.run_sync(lambda sync_conn: {
                column["name"] for column in inspect(sync_conn).get_columns("approval_requests")
            })
            if "published_image_urn" not in approval_columns:
                await conn.execute(text("ALTER TABLE approval_requests ADD COLUMN published_image_urn VARCHAR(255)"))

            # Encrypt any legacy LinkedIn tokens exactly once per deployment instance.
            # New connections are encrypted before they are persisted.
            # This is deliberately best-effort for existing local test databases.
            retired_columns = {"audience", "goals", "brand_positioning"}
            for column_name in retired_columns.intersection(columns):
                try:
                    await conn.execute(text(f'ALTER TABLE user_profiles DROP COLUMN "{column_name}"'))
                except Exception:
                    logger.warning("Could not drop retired user_profiles.%s", column_name)

            brand_memory_columns = await conn.run_sync(lambda sync_conn: {
                column["name"] for column in inspect(sync_conn).get_columns("brand_memory")
            })
            if "audience_json" in brand_memory_columns:
                try:
                    await conn.execute(text('ALTER TABLE brand_memory DROP COLUMN "audience_json"'))
                except Exception:
                    logger.warning("Could not drop retired brand_memory.audience_json")

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(
            sync_conn,
            tables=[ObservabilityEvent.__table__, UserFeedback.__table__, JobSearchCache.__table__],
            checkfirst=True,
        ))
        # Roles are application data and must remain under explicit account
        # administration. Never rewrite auth_users.role during application
        # startup: doing so can silently undo an intentional role change.

    try:
        async with SessionLocal() as security_session:
            await migrate_plaintext_linkedin_tokens(security_session)
    except Exception:
        logger.exception("LinkedIn token migration failed")
        raise

    # Vercel functions are ephemeral. Supabase Cron owns scheduled execution
    # in the Vercel deployment, so never start an in-process scheduler there.
    if settings.agent_in_process_schedule_enabled and not vercel_runtime:
        agent_scheduler.start()
    yield
    if settings.agent_in_process_schedule_enabled and not vercel_runtime:
        await agent_scheduler.stop()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def restore_vercel_api_prefix(request: Request, call_next):
    """Vercel Services strips the public /api prefix before invoking this service."""
    if os.getenv("VERCEL", "").lower() == "1":
        path = request.scope.get("path", "")
        if not path.startswith("/api"):
            restored = "/api" + (path if path.startswith("/") else f"/{path}")
            request.scope["path"] = restored
            request.scope["raw_path"] = restored.encode("utf-8")
    return await call_next(request)


@app.middleware("http")
async def security_controls(request: Request, call_next):
    """Apply API rate limits, cookie-session CSRF protection and security headers."""
    path = request.scope.get("path", "")
    method = request.method.upper()
    response = None

    if path.startswith("/api/") and method != "OPTIONS":
        if not path.startswith("/api/health"):
            limit, window = endpoint_limit(path, method)
            token = request.cookies.get(SESSION_COOKIE) or request.headers.get("authorization", "")
            identity = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24] if token else client_key(request)
            limiter_key = f"{identity}:{method}:{path}"
            if not rate_limiter.allow(limiter_key, limit, window):
                security_event("rate_limited", request, method=method)
                response = JSONResponse(
                    {"detail": "Too many requests. Please try again later."},
                    status_code=429,
                    headers={"Retry-After": str(window)},
                )

        if response is None and method not in {"GET", "HEAD"}:
            public_csrf_paths = {"/api/auth/linkedin/exchange"}
            has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
            session_token = request.cookies.get(SESSION_COOKIE)
            if session_token and not has_bearer and path not in public_csrf_paths:
                supplied = request.headers.get("X-CSRF-Token")
                cookie_value = request.cookies.get(CSRF_COOKIE)
                if not validate_csrf_token(session_token, supplied, cookie_value):
                    security_event("csrf_failed", request, method=method)
                    response = JSONResponse({"detail": "CSRF validation failed."}, status_code=403)

    if response is None:
        response = await call_next(request)

    response.headers["X-Request-ID"] = secrets.token_hex(16)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response



class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    topic: str
    pillar: str = "Expertise"
    body: str


class ImproveContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    topic: str = ""
    body: str
    language: str | None = None


class StrategyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str | None = None
    sources: list[dict[str, str]] = Field(default_factory=list)


class LearningThoughtRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str
    topic: str | None = None
    title: str | None = None


class LearningThoughtDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[int] = Field(default_factory=list)


class VoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_examples: list[str]


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = "User"
    professional_title: str
    industry: str
    tone: str
    experience_years: float = Field(ge=0, le=100)


class BrandOnboardingPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    published_at: str | None = None
    external_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class BrandOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = "User"
    professional_title: str = ""
    industry: str = ""
    tone: str = ""
    experience_years: float | None = Field(default=None, ge=0, le=100)
    posts: list[BrandOnboardingPost] = Field(default_factory=list)


class ApprovalEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edited_body: str
    reason: str | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class LinkedInExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    oauth_nonce: str | None = None


class AccountDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str



class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_type: str = Field(min_length=2, max_length=40)
    subject: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=2, max_length=5000)
    context: str | None = Field(default=None, max_length=1000)


class FeedbackStatusRequest(BaseModel):
    status: str
    priority: str | None = None


@app.get("/api/jobs/search")
async def jobs_search(
    request: Request,
    query: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)
    linkedin_result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == int(current_user.id))
    )
    linkedin_connection = linkedin_result.scalar_one_or_none()
    location = resolve_job_location(
        request,
        linkedin_connection.linkedin_locale if linkedin_connection else None,
        default_country=settings.adzuna_country,
    )
    return await search_jobs(
        session,
        profile.professional_title or "",
        profile.experience_years,
        profile.industry or "",
        query,
        location=location,
    )


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest, session: AsyncSession = Depends(get_session),
                          current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user"))):
    if req.feedback_type not in {"BUG", "FEATURE", "GENERAL", "OTHER"}:
        raise HTTPException(status_code=400, detail="Unsupported feedback type.")
    feedback = UserFeedback(user_id=int(current_user.id), feedback_type=req.feedback_type,
                            subject=req.subject.strip(), description=req.description.strip(),
                            context=(req.context or "").strip()[:1000] or None)
    session.add(feedback)
    session.add(AuditLog(event_type="FEEDBACK_SUBMITTED", actor=str(current_user.id),
                         payload=json.dumps({"feedback_type": req.feedback_type, "subject": req.subject[:200]})))
    await session.commit()
    return {"id": feedback.id, "status": feedback.status}


@app.get("/api/feedback")
async def list_my_feedback(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user"))):
    rows = (await session.execute(select(UserFeedback).where(UserFeedback.user_id == int(current_user.id)).order_by(UserFeedback.created_at.desc()).limit(50))).scalars().all()
    return {"items": [{"id": x.id, "type": x.feedback_type, "subject": x.subject, "description": x.description,
                       "status": x.status, "priority": x.priority, "created_at": x.created_at} for x in rows]}


@app.get("/api/admin/overview")
async def admin_overview(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin"))):
    total_users = len((await session.execute(select(AuthUser.id))).scalars().all())
    active_users = len((await session.execute(select(AuthUser.id).where(AuthUser.is_active == True))).scalars().all())
    total_events = len((await session.execute(select(ObservabilityEvent.id))).scalars().all())
    failed = len((await session.execute(select(ObservabilityEvent.id).where(ObservabilityEvent.status == "FAILED"))).scalars().all())
    successful = len((await session.execute(select(ObservabilityEvent.id).where(ObservabilityEvent.status == "SUCCESS"))).scalars().all())
    total_feedback = len((await session.execute(select(UserFeedback.id))).scalars().all())
    open_feedback = len((await session.execute(select(UserFeedback.id).where(UserFeedback.status.in_(["NEW", "REVIEWING", "PLANNED", "IN_PROGRESS"])))).scalars().all())
    return {"users": {"total": total_users, "active": active_users},
            "reliability": {"events": total_events, "successful_requests": successful, "failed_requests": failed, "error_rate": failed / total_events if total_events else 0},
            "feedback": {"total": total_feedback, "open": open_feedback},
            "ai_providers": {"groq": bool(settings.groq_api_key), "openrouter": bool(settings.openrouter_api_key), "gemini": bool(settings.gemini_api_key)},
            "job_providers": {"Adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key), "Jooble": bool(settings.jooble_api_key), "The Muse": bool(settings.themuse_api_key), "Remotive": bool(settings.remotive_enabled)}}


@app.get("/api/admin/users")
async def admin_users(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin"))):
    users = (await session.execute(select(AuthUser).order_by(AuthUser.created_at.desc()).limit(500))).scalars().all()
    return {"items": [{"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role,
                       "active": u.is_active, "whitelisted": u.is_whitelisted, "created_at": u.created_at} for u in users]}


@app.get("/api/admin/failures")
async def admin_failures(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin"))):
    rows = (await session.execute(select(ObservabilityEvent).where(ObservabilityEvent.status == "FAILED").order_by(ObservabilityEvent.created_at.desc()).limit(100))).scalars().all()
    return {"items": [{"id": x.id, "user_id": x.user_id, "correlation_id": x.correlation_id, "event_type": x.event_type,
                       "activity_type": x.activity_type, "status": x.status, "failure_category": x.failure_category,
                       "http_status": x.http_status, "latency_ms": x.latency_ms, "provider": x.provider,
                       "fallback_used": x.fallback_used, "final_provider": x.final_provider, "created_at": x.created_at,
                       "details": json.loads(x.details_json or "{}")} for x in rows]}


@app.get("/api/admin/feedback")
async def admin_feedback(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin"))):
    rows = (await session.execute(select(UserFeedback).order_by(UserFeedback.created_at.desc()).limit(300))).scalars().all()
    return {"items": [{"id": x.id, "user_id": x.user_id, "type": x.feedback_type, "subject": x.subject,
                       "description": x.description, "context": x.context, "status": x.status, "priority": x.priority,
                       "created_at": x.created_at, "updated_at": x.updated_at} for x in rows]}


@app.patch("/api/admin/feedback/{feedback_id}")
async def admin_update_feedback(feedback_id: int, req: FeedbackStatusRequest, session: AsyncSession = Depends(get_session),
                                current_user: AppUser = Depends(require_roles("admin"))):
    if req.status not in {"NEW", "REVIEWING", "PLANNED", "IN_PROGRESS", "RESOLVED", "DUPLICATE", "NOT_PLANNED"}:
        raise HTTPException(status_code=400, detail="Invalid feedback status.")
    if req.priority and req.priority not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise HTTPException(status_code=400, detail="Invalid feedback priority.")
    item = (await session.execute(select(UserFeedback).where(UserFeedback.id == feedback_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    item.status = req.status
    if req.priority:
        item.priority = req.priority
    session.add(AuditLog(event_type="FEEDBACK_UPDATED", actor=str(current_user.id),
                         payload=json.dumps({"feedback_id": feedback_id, "status": req.status, "priority": req.priority})))
    await session.commit()
    return {"id": item.id, "status": item.status, "priority": item.priority}


@app.get("/api/admin/ai-providers")
async def admin_ai_providers(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin"))):
    return {"configured": {"groq": bool(settings.groq_api_key), "openrouter": bool(settings.openrouter_api_key), "gemini": bool(settings.gemini_api_key)}}

@app.get("/api/admin/job-providers")
async def admin_job_providers(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin"))):
    return {"configured": {"Adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key), "Jooble": bool(settings.jooble_api_key), "The Muse": bool(settings.themuse_api_key), "Remotive": bool(settings.remotive_enabled)}}

@app.middleware("http")
async def observability_controls(request: Request, call_next):
    path = request.scope.get("path", "")
    if not path.startswith("/api/") or path.startswith("/api/health"):
        return await call_next(request)
    started = datetime.now(timezone.utc)
    correlation_id = request.headers.get("x-correlation-id") or secrets.token_hex(12)
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        try:
            token = request_token(request)
            async with SessionLocal() as telemetry_session:
                user_id = None
                if token:
                    user = await AuthService.get_user_from_token(telemetry_session, token)
                    if user and str(user.id).isdigit():
                        user_id = int(user.id)
                elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                method = request.method.upper()
                activity = "OTHER"
                if "/content/" in path: activity = "GENERATE"
                elif "/research/" in path: activity = "RESEARCH"
                elif "/approvals/" in path: activity = "PUBLISH"
                elif "/learning/" in path: activity = "LEARNING"
                elif "/linkedin/" in path: activity = "LINKEDIN_CONNECT"
                elif "/auth/" in path: activity = "AUTHENTICATION"
                elif "/jobs" in path: activity = "JOB_SEARCH"
                status = "SUCCESS" if status_code < 400 else "FAILED"
                category = "RATE_LIMIT" if status_code == 429 else ("AUTHENTICATION_ERROR" if status_code == 401 else ("AUTHORIZATION_ERROR" if status_code == 403 else ("UNKNOWN" if status_code >= 500 else None)))
                telemetry_session.add(ObservabilityEvent(
                    user_id=user_id, correlation_id=correlation_id,
                    event_type="RequestSucceeded" if status == "SUCCESS" else "RequestFailed",
                    activity_type=activity, status=status, user_visible_failure=status == "FAILED",
                    failure_category=category, http_status=status_code, latency_ms=elapsed,
                    details_json=json.dumps({"method": method, "path": path[:180]}, ensure_ascii=False),
                ))
                await telemetry_session.commit()
        except Exception:
            logger.exception("Observability event recording failed")

@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "external_actions": "approval_required",
        "agent_enabled": settings.agent_enabled,
        "agent_modes": ["daily_discovery", "event_driven", "scheduled_calendar"],
    }


@app.get("/health/ready")
async def readiness() -> dict[str, object]:
    """Dependency-aware readiness probe for controlled Render fallback/cutover."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "ok",
            "environment": settings.environment,
        }
    except Exception:
        logger.exception("Readiness check failed")
        raise HTTPException(status_code=503, detail="Service dependencies are not ready")


@app.get("/api/auth/linkedin/start")
async def linkedin_oauth_start(
    browser_nonce: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if browser_nonce and len(browser_nonce) > 200:
        raise HTTPException(status_code=400, detail="Invalid OAuth browser nonce.")
    url, state = await build_authorization_url(session, browser_nonce=browser_nonce)
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        key="brand_os_oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=settings.is_production,
        # LinkedIn is a cross-site OAuth provider. None+Secure is supported
        # by modern browsers and avoids embedded/mobile browser cookie loss.
        samesite="none" if settings.is_production else "lax",
        path="/",
    )
    return response


@app.get("/api/auth/linkedin/callback")
async def linkedin_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if error:
        response = RedirectResponse(
            url=f"{(settings.frontend_url or 'http://localhost:3000').rstrip('/')}/?linkedin_error=authorization_denied",
            status_code=302,
        )
        response.delete_cookie("brand_os_oauth_state", path="/api")
        return response
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing LinkedIn OAuth code or state.")

    # The server-side state record is the authoritative one-time OAuth
    # transaction. Do not require the browser cookie here because some mobile
    # browsers and embedded OAuth handoffs can drop cookies across the
    # LinkedIn -> Suvacya redirect. The frontend separately validates the
    # browser nonce before exchanging the one-time code for a Suvacya session.
    expected_state = request.cookies.get("brand_os_oauth_state") if request else None
    if expected_state and not secrets.compare_digest(expected_state, state):
        logger.warning("LinkedIn OAuth state cookie mismatch; continuing with server-side state validation.")

    browser_nonce = state.split(".", 1)[1] if "." in state else None
    exchange = await handle_callback(session, code, state)
    frontend = (
        "https://linkedin-brand-os-alpha.vercel.app"
        if settings.is_production
        else (settings.frontend_url or "http://localhost:3000")
    ).rstrip("/")
    nonce_suffix = f"&oauth_nonce={browser_nonce}" if browser_nonce else ""
    response = RedirectResponse(url=f"{frontend}/?linkedin_code={exchange}{nonce_suffix}", status_code=302)
    # Keep the short-lived state cookie until the browser exchanges the one-time
    # code. This lets the server bind the exchange to the browser that started OAuth.
    return response


@app.post("/api/auth/linkedin/exchange")
async def linkedin_oauth_exchange(
    request: Request,
    req: LinkedInExchangeRequest,
    session: AsyncSession = Depends(get_session),
):
    # The exchange code is a short-lived, single-use server-side credential
    # created only after LinkedIn has validated the OAuth state and member
    # identity. Do not require the original browser cookie here: mobile
    # browsers can legitimately drop cross-site cookies during the LinkedIn
    # -> Suvacya redirect.
    if not req.oauth_nonce:
        raise HTTPException(status_code=400, detail="LinkedIn exchange is missing the browser nonce.")
    result = await exchange_code(session, req.code, req.oauth_nonce)
    response = JSONResponse({
        "success": True,
        "display_name": result["display_name"],
        "role": result["role"],
        "email": result["email"],
    })
    set_session_cookies(response, result["token"])
    response.delete_cookie("brand_os_oauth_state", path="/")
    return response


@app.get("/api/linkedin/status")
async def linkedin_status(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    user = await AuthService.get_user_from_token(session, request_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == int(user.id))
    )
    connection = result.scalar_one_or_none()
    missing_profile_fields = []
    if connection is not None:
        missing_profile_fields = [
            field for field, value in (
                ("headline", connection.linkedin_headline),
                ("picture_url", connection.linkedin_picture_url),
                ("locale", connection.linkedin_locale),
                ("vanity_name", connection.linkedin_vanity_name),
            ) if not value or not str(value).strip()
        ]
    return {
        "connected": connection is not None,
        "name": connection.linkedin_name if connection else None,
        "email": connection.linkedin_email if connection else None,
        "expires_at": connection.token_expires_at if connection else None,
        "profile_sync_needed": bool(missing_profile_fields),
        "missing_profile_fields": missing_profile_fields,
    }


@app.post("/api/linkedin/profile/sync-missing")
async def sync_missing_linkedin_profile(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    user = await AuthService.get_user_from_token(session, request_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await sync_missing_profile_data(session, int(user.id))


@app.post("/api/auth/linkedin/login")
async def linkedin_login_legacy():
    raise HTTPException(
        status_code=410,
        detail="Legacy LinkedIn login is disabled. Use the official LinkedIn OAuth flow.",
    )


@app.get("/api/auth/me")
async def auth_me(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    token = request_token(request)
    if token is None:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    user = await AuthService.get_user_from_token(session, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "display_name": user.display_name,
        "linkedin_url": user.linkedin_url,
    }


@app.post("/api/auth/logout")
async def auth_logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    token = request_token(request)
    if token:
        token_hash = AuthService.hash_token(token)
        result = await session.execute(select(AuthSession).where(AuthSession.token_hash == token_hash))
        session_row = result.scalar_one_or_none()
        if session_row is not None:
            await session.delete(session_row)
            await session.commit()
    response = JSONResponse({"success": True})
    clear_session_cookies(response)
    return response

@app.get("/api/account/export")
async def export_account(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile_id = int(current_user.id)
    profile = await session.get(UserProfile, profile_id)
    brand = (await session.execute(select(BrandMemory).where(BrandMemory.profile_id == profile_id))).scalar_one_or_none()
    voice = (await session.execute(select(VoiceMemory).where(VoiceMemory.profile_id == profile_id))).scalar_one_or_none()
    linkedin = (await session.execute(select(LinkedInConnection).where(LinkedInConnection.user_id == profile_id))).scalar_one_or_none()
    historical = (await session.execute(select(HistoricalPost).where(HistoricalPost.profile_id == profile_id))).scalars().all()
    content_items = (await session.execute(select(ContentItem).where(ContentItem.profile_id == profile_id))).scalars().all()
    versions = []
    for item in content_items:
        versions.extend((await session.execute(select(ContentVersion).where(ContentVersion.content_id == item.id))).scalars().all())
    approvals = []
    if versions:
        approvals = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.content_version_id.in_([v.id for v in versions])))).scalars().all()
    feedback = []
    if versions:
        feedback = (await session.execute(select(FeedbackEntry).where(FeedbackEntry.content_version_id.in_([v.id for v in versions])))).scalars().all()
    events = (await session.execute(select(LearningEvent).where(LearningEvent.profile_id == profile_id))).scalars().all()
    memories = (await session.execute(select(LearningMemory).where(LearningMemory.profile_id == profile_id))).scalars().all()
    sources = (await session.execute(select(ResearchSource).where(ResearchSource.profile_id == profile_id))).scalars().all()
    opportunities = (await session.execute(select(ContentOpportunity).where(ContentOpportunity.profile_id == profile_id))).scalars().all()

    def model_dict(row):
        if row is None:
            return None
        return {
            key: (value.isoformat() if isinstance(value, datetime) else value)
            for key, value in row.__dict__.items()
            if key != "_sa_instance_state"
        }

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {"id": current_user.id, "email": current_user.email, "role": current_user.role, "display_name": current_user.display_name},
        "profile": model_dict(profile),
        "brand_memory": model_dict(brand),
        "voice_memory": model_dict(voice),
        "linkedin_connection": {
            "connected": linkedin is not None,
            "member_sub": linkedin.member_sub if linkedin else None,
            "email": linkedin.linkedin_email if linkedin else None,
            "name": linkedin.linkedin_name if linkedin else None,
            "headline": linkedin.linkedin_headline if linkedin else None,
            "picture_url": linkedin.linkedin_picture_url if linkedin else None,
            "locale": linkedin.linkedin_locale if linkedin else None,
            "vanity_name": linkedin.linkedin_vanity_name if linkedin else None,
            "token_expires_at": linkedin.token_expires_at if linkedin else None,
        },
        "historical_posts": [model_dict(row) for row in historical],
        "content_items": [model_dict(row) for row in content_items],
        "content_versions": [model_dict(row) for row in versions],
        "approvals": [model_dict(row) for row in approvals],
        "feedback": [model_dict(row) for row in feedback],
        "learning_events": [model_dict(row) for row in events],
        "learning_memories": [model_dict(row) for row in memories],
        "research_sources": [model_dict(row) for row in sources],
        "content_opportunities": [model_dict(row) for row in opportunities],
    }


@app.delete("/api/account")
async def delete_account(
    req: AccountDeletionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    if req.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm account deletion.")

    user_id = int(current_user.id)
    profile_id = user_id

    # Delete dependent data explicitly so the workflow is idempotent even where
    # older migrations did not declare ON DELETE CASCADE.
    content_ids = [row[0] for row in (await session.execute(
        select(ContentItem.id).where(ContentItem.profile_id == profile_id)
    )).all()]
    version_ids = [row[0] for row in (await session.execute(
        select(ContentVersion.id).where(ContentVersion.content_id.in_(content_ids))
    )).all()] if content_ids else []

    if version_ids:
        await session.execute(delete(FeedbackEntry).where(FeedbackEntry.content_version_id.in_(version_ids)))
        await session.execute(delete(ApprovalRequest).where(ApprovalRequest.content_version_id.in_(version_ids)))
        await session.execute(delete(ContentVersion).where(ContentVersion.id.in_(version_ids)))
    if content_ids:
        await session.execute(delete(ContentItem).where(ContentItem.id.in_(content_ids)))

    for model, column in [
        (HistoricalPost, HistoricalPost.profile_id),
        (ResearchSource, ResearchSource.profile_id),
        (ContentOpportunity, ContentOpportunity.profile_id),
        (LearningEvent, LearningEvent.profile_id),
        (LearningMemory, LearningMemory.profile_id),
        (DurableJob, DurableJob.profile_id),
        (AgentRun, AgentRun.user_id),
        (VoiceMemory, VoiceMemory.profile_id),
        (BrandMemory, BrandMemory.profile_id),
        (AuthSession, AuthSession.user_id),
        (LinkedInOAuthExchange, LinkedInOAuthExchange.user_id),
        (LinkedInConnection, LinkedInConnection.user_id),
        (UserProfile, UserProfile.id),
    ]:
        await session.execute(delete(model).where(column == profile_id))

    # Security/audit records are not part of the user's content export and may
    # be retained only when needed for incident/compliance purposes. Remove
    # records whose actor is directly identifiable as this account.
    await session.execute(
        delete(AuditLog).where(
            (AuditLog.actor == str(user_id)) | (AuditLog.actor == current_user.email)
        )
    )
    await session.execute(delete(AuthUser).where(AuthUser.id == user_id))
    await session.commit()

    response = JSONResponse({"success": True, "message": "Your Suvacya account and application data have been deleted."})
    clear_session_cookies(response)
    return response


@app.get("/api/profile")
async def get_profile(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)
    await session.commit()
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "professional_title": profile.professional_title,
        "industry": profile.industry,
        "experience_years": profile.experience_years,
        "tone": profile.tone,
        "role": profile.role or "owner",
    }


@app.post("/api/profile")
async def upsert_profile_legacy():
    raise HTTPException(
        status_code=410,
        detail="Use the Brand DNA setup to enter your professional title, industry, desired tone and years of experience.",
    )


@app.get("/api/brand/status")
async def brand_status(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    service = BrandIntelligenceService(session)
    profile = await AuthService.get_or_create_profile(session, current_user)
    memory = await service.ensure_profile_memory(profile.id)
    posts = await service.get_posts(profile.id, limit=100)
    profile_complete = bool(
        profile.professional_title and profile.professional_title.strip()
        and profile.industry and profile.industry.strip()
        and profile.tone and profile.tone.strip()
    )
    brand_ready = bool(memory and memory.status == "READY" and profile_complete)
    linkedin_result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == int(profile.id)).limit(1)
    )
    linkedin_connection = linkedin_result.scalar_one_or_none()
    return {
        "status": "READY" if brand_ready else ("NEEDS_INPUT" if memory else "NOT_INITIALIZED"),
        "ready": brand_ready,
        "source_post_count": memory.source_post_count if memory else len(posts),
        "current_post_count": len(posts),
        "summary": memory.summary if memory else None,
        "continuous_learning": True,
        "historical_import_optional": True,
        "brand_bootstrap_completed": bool(profile.brand_bootstrap_completed),
        "last_updated": memory.updated_at if memory else None,
        "profile": {
            "display_name": profile.display_name if profile else "User",
            "professional_title": profile.professional_title if profile else None,
            "industry": profile.industry if profile else None,
            "experience_years": profile.experience_years if profile else None,
            "tone": profile.tone if profile else None,
        },
        "linkedin_profile": {
            "connected": bool(linkedin_connection),
            "headline": linkedin_connection.linkedin_headline if linkedin_connection else None,
            "picture_url": linkedin_connection.linkedin_picture_url if linkedin_connection else None,
            "locale": linkedin_connection.linkedin_locale if linkedin_connection else None,
            "vanity_name": linkedin_connection.linkedin_vanity_name if linkedin_connection else None,
        },
        "source_posts": [
            {"id": post.id, "body": post.body, "published_at": post.published_at, "source": post.source}
            for post in posts
            if post.source == "user_import"
        ][:10],
    }


@app.post("/api/brand/bootstrap")
async def brand_bootstrap(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    """Seed Brand DNA from the official LinkedIn profile data we already receive.

    This is deliberately best-effort. Authentication must never depend on the
    model provider, and we never overwrite fields the user has already set.
    Historical LinkedIn posts are not requested here because that permission is
    not available to the current app.
    """
    profile = await AuthService.get_or_create_profile(session, current_user)
    connection_result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == int(current_user.id)).limit(1)
    )
    connection = connection_result.scalar_one_or_none()
    if connection is None:
        return {"bootstrapped": False, "reason": "linkedin_not_connected"}

    if profile.brand_bootstrap_completed:
        memory = await BrandIntelligenceService(session).get_memory(profile.id)
        return {
            "bootstrapped": True,
            "already_completed": True,
            "ready": bool(
                memory and memory.status == "READY"
                and profile.professional_title and profile.industry and profile.tone
            ),
        }

    # Use the headline directly when LinkedIn provides it. It is the strongest
    # self-authored professional signal available through the current open profile scope.
    if connection.linkedin_headline and not profile.professional_title:
        profile.professional_title = connection.linkedin_headline[:200]

    if not profile.tone:
        profile.tone = "Clear, practical and credible"

    existing_memory = await BrandIntelligenceService(session).get_memory(profile.id)
    if (
        profile.professional_title
        and profile.industry
        and profile.tone
        and existing_memory
        and existing_memory.status == "READY"
    ):
        profile.brand_bootstrap_completed = True
        await session.commit()
        return {
            "bootstrapped": True,
            "already_completed": False,
            "ready": True,
            "profile": {
                "display_name": profile.display_name,
                "professional_title": profile.professional_title,
                "industry": profile.industry,
                "experience_years": profile.experience_years,
                "tone": profile.tone,
            },
        }

    inferred = {}
    if connection.linkedin_headline or profile.professional_title:
        system = """You create a conservative first-pass Brand DNA profile from a user's
own LinkedIn authentication data.

Rules:
- Use only the supplied LinkedIn name, headline, locale and existing profile fields.
- Never invent employers, credentials, achievements, years of experience, clients or facts.
- Infer an industry only when the headline/profile gives enough evidence. Otherwise return an empty string.
- A professional title may be cleaned up from the headline, but do not add claims.
- Tone is a writing preference, not a fact. Only suggest a simple neutral tone if the profile gives a clear signal; otherwise return an empty string.
- Never infer years of experience from a title or seniority word.
- Return JSON only:
{"professional_title":"","industry":"","tone":""}
"""
        prompt = json.dumps(
            {
                "name": profile.display_name,
                "linkedin_headline": connection.linkedin_headline,
                "linkedin_locale": connection.linkedin_locale,
                "existing_professional_title": profile.professional_title,
                "existing_industry": profile.industry,
                "existing_tone": profile.tone,
            },
            ensure_ascii=False,
        )
        try:
            inferred = await ModelRouterService().generate_json(system, prompt, max_output_tokens=500)
        except Exception as exc:
            logger.warning("LinkedIn Brand DNA bootstrap model unavailable: %s", exc)

    if not profile.professional_title and str(inferred.get("professional_title") or "").strip():
        profile.professional_title = str(inferred["professional_title"]).strip()[:200]
    if not profile.industry and str(inferred.get("industry") or "").strip():
        profile.industry = str(inferred["industry"]).strip()[:200]
    if not profile.tone and str(inferred.get("tone") or "").strip():
        profile.tone = str(inferred["tone"]).strip()[:200]

    profile.brand_bootstrap_completed = True
    await session.commit()

    # Do not build Brand Intelligence before the user reviews the draft.
    # This keeps onboarding to at most one lightweight inference call and
    # preserves the user's final say over the saved Brand DNA.
    ready_for_review = bool(profile.professional_title and profile.industry and profile.tone)

    return {
        "bootstrapped": True,
        "already_completed": False,
        "ready": False,
        "ready_for_review": ready_for_review,
        "profile": {
            "display_name": profile.display_name,
            "professional_title": profile.professional_title,
            "industry": profile.industry,
            "experience_years": profile.experience_years,
            "tone": profile.tone,
        },
        "linkedin_profile": {
            "headline": connection.linkedin_headline,
            "picture_url": connection.linkedin_picture_url,
            "locale": connection.linkedin_locale,
            "vanity_name": connection.linkedin_vanity_name,
        },
    }


@app.get("/api/brand/memory")
async def brand_memory(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    service = BrandIntelligenceService(session)
    profile = await AuthService.get_or_create_profile(session, current_user)
    return service.serialize(await service.get_memory(profile.id))


@app.get("/api/brand/source-posts")
async def brand_source_posts(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)
    result = await session.execute(
        select(HistoricalPost)
        .where(HistoricalPost.profile_id == int(profile.id), HistoricalPost.source == "user_import")
        .order_by(HistoricalPost.created_at.asc())
        .limit(10)
    )
    return {"posts": [
        {"id": post.id, "body": post.body, "published_at": post.published_at, "source": post.source}
        for post in result.scalars().all()
    ]}


@app.post("/api/brand/onboard")
async def brand_onboard(
    req: BrandOnboardingRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "user")),
):

    if len(req.posts) > 10:
        raise HTTPException(status_code=400, detail="You can import a maximum of 10 previous posts.")
    if any(not post.body.strip() for post in req.posts):
        raise HTTPException(status_code=400, detail="Every imported post must contain content.")

    profile = await AuthService.get_or_create_profile(session, current_user)

    # LinkedIn-assisted onboarding is additive. Existing user-entered Brand DNA
    # remains authoritative, while blank fields can be supplied from the current
    # onboarding draft. Experience is optional because LinkedIn's open profile
    # scopes do not expose employment history.
    profile.display_name = req.display_name.strip()[:150] or current_user.display_name or profile.display_name or "User"
    if req.professional_title.strip():
        profile.professional_title = req.professional_title.strip()[:200]
    if req.industry.strip():
        profile.industry = req.industry.strip()[:200]
    if req.experience_years is not None:
        profile.experience_years = float(req.experience_years)
    if req.tone.strip():
        profile.tone = req.tone.strip()[:200]
    profile.role = profile.role or current_user.role or "user"
    await session.commit()

    # Historical posts are optional. If the user supplies them, replace only
    # the editable user-import set. An empty submission preserves existing
    # imported evidence rather than deleting it.
    import_result = {"created": 0, "skipped": 0, "total": 0}
    service = BrandIntelligenceService(session)
    if req.posts:
        await session.execute(
            delete(HistoricalPost).where(
                HistoricalPost.profile_id == int(profile.id),
                HistoricalPost.source == "user_import",
            )
        )
        await session.commit()
        import_result = await service.import_posts(
            [
                {
                    "body": post.body,
                    "published_at": post.published_at,
                    "external_id": post.external_id,
                    "metadata": post.metadata,
                    "source": "user_import",
                }
                for post in req.posts
            ],
            profile_id=profile.id,
        )
    try:
        memory = await service.analyze(profile.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Brand onboarding analysis failed: %s", exc)
        raise HTTPException(status_code=502, detail="Brand analysis failed. Neither configured LLM provider returned a usable analysis. Please try again; your imported posts were saved.") from exc

    return {"import": import_result, "brand_memory": memory}


@app.post("/api/brand/initialize")
async def brand_initialize_legacy():
    raise HTTPException(
        status_code=410,
        detail="Automatic Brand DNA initialization is disabled. Use LinkedIn-assisted onboarding and review the generated Brand DNA.",
    )


@app.post("/api/brand/rebuild")
async def rebuild_brand(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)
    service = BrandIntelligenceService(session)
    try:
        return await service.analyze(profile.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Brand analysis failed. Check the configured LLM providers and try again.") from exc


@app.get("/api/dashboard/approvals")
async def dashboard_approvals(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    approval_service = ApprovalService(session)
    approvals = await approval_service.list_dashboard(int(current_user.id))
    counts = await approval_service.dashboard_counts(int(current_user.id))
    records = []
    if approvals:
        version_ids = [item.content_version_id for item in approvals]
        content_result = await session.execute(
            select(ContentVersion, ContentItem)
            .join(ContentItem, ContentItem.id == ContentVersion.content_id)
            .where(ContentVersion.id.in_(version_ids))
        )
        content_by_version = {
            int(version.id): (version, content_item)
            for version, content_item in content_result.all()
        }
        for item in approvals:
            version, content_item = content_by_version.get(item.content_version_id, (None, None))
            records.append(
                {
                    "id": item.id,
                    "status": item.status,
                    "action_type": item.action_type,
                    "reason": item.reason,
                    "content": version.body if version else "",
                    "title": content_item.title if content_item else "",
                    "topic": content_item.topic if content_item else "",
                    "approved_at": item.approved_at,
                    "created_at": item.created_at,
                }
            )
    return {"pending_approvals": records, "counts": counts}


@app.get("/api/agent/status")
async def agent_status(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    result = await session.execute(
        select(AgentRun)
        .where(AgentRun.user_id == int(current_user.id))
        .order_by(AgentRun.started_at.desc())
        .limit(10)
    )
    runs = result.scalars().all()
    return {
        "enabled": settings.agent_enabled,
        "modes": {
            "daily_discovery": settings.agent_daily_discovery_enabled,
            "event_driven": True,
            "scheduled_calendar": settings.agent_calendar_enabled,
        },
        "recent_runs": [
            {
                "id": run.id,
                "mode": run.mode,
                "trigger": run.trigger,
                "status": run.status,
                "created_count": run.created_count,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "details": run.details,
            }
            for run in runs
        ],
    }


class AgentEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    payload: dict[str, object] = Field(default_factory=dict)


async def _require_scheduled_job_key(x_brand_os_job_key: str | None = Header(default=None)) -> None:
    expected = settings.scheduled_job_key
    if not expected or not x_brand_os_job_key or not secrets.compare_digest(x_brand_os_job_key, expected):
        raise HTTPException(status_code=401, detail="Invalid scheduled job credentials.")


async def _run_scheduled_job_background(job_name: str) -> None:
    jobs = ScheduledJobs(SessionLocal)
    if job_name in {"discovery", "calendar"}:
        try:
            result = await jobs.run(job_name)
            logger.info("Scheduled %s job completed: %s", job_name, result)
        except Exception:
            logger.exception("Scheduled %s job failed.", job_name)
        return

    async with SessionLocal() as session:
        try:
            result = await jobs.process_retention(session)
            await session.commit()
            logger.info("Scheduled retention job completed: %s", result)
        except Exception:
            await session.rollback()
            logger.exception("Scheduled retention job failed.")




_scheduled_background_tasks: set[asyncio.Task] = set()


def _dispatch_scheduled_job(job_name: str) -> None:
    task = asyncio.create_task(_run_scheduled_job_background(job_name))
    _scheduled_background_tasks.add(task)
    task.add_done_callback(_scheduled_background_tasks.discard)


@app.post("/api/internal/scheduled-jobs/{job_name}")
async def run_scheduled_job(
    job_name: str,
    _: None = Depends(_require_scheduled_job_key),
):
    jobs = ScheduledJobs(SessionLocal)
    if job_name not in {"discovery", "calendar", "retention", "learning"}:
        raise HTTPException(status_code=404, detail="Unknown scheduled job.")

    if job_name == "learning":
        if settings.durable_learning_worker_enabled:
            local_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
            async with SessionLocal() as session:
                job = await enqueue_job(
                    session,
                    job_type="brand_learning_event",
                    payload={"scheduled_date": local_date},
                    idempotency_key=f"scheduled:learning:{local_date}",
                )
                await session.commit()
            return {
                "ok": True,
                "job": job_name,
                "accepted": True,
                "queued": True,
                "job_id": job.id if job else None,
            }

        async with SessionLocal() as session:
            try:
                processed = await jobs.process_learning(session, limit=50)
                await session.commit()
                logger.info("Scheduled learning job completed: processed=%s", processed)
            except Exception:
                await session.rollback()
                logger.exception("Scheduled learning job failed.")
        return

    if settings.durable_scheduled_worker_enabled:
        local_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        async with SessionLocal() as session:
            job = await enqueue_job(
                session,
                job_type=f"scheduled_{job_name}",
                payload={"mode": job_name, "scheduled_date": local_date},
                idempotency_key=f"scheduled:{job_name}:{local_date}",
            )
            await session.commit()
        return {
            "ok": True,
            "job": job_name,
            "accepted": True,
            "queued": True,
            "job_id": job.id if job else None,
        }

    # Safe fallback while the durable worker is disabled. Supabase pg_net gets
    # a fast response while the existing AgentRun/idempotency guards protect
    # the actual scheduled work.
    _dispatch_scheduled_job(job_name)
    return {"ok": True, "job": job_name, "accepted": True, "queued": False}

@app.post("/api/agent/events")
async def trigger_agent_event(
    req: AgentEventRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "user")),
):
    run = AgentRun(user_id=int(current_user.id), mode="event", trigger=f"event:{req.event_type}", status="RUNNING")
    session.add(run)
    await session.flush()
    try:
        orchestrator = AgentOrchestrator(session, int(current_user.id))
        if req.event_type == "manual_generate_content":
            result = await orchestrator.run_manual_content_generation()
        else:
            result = await orchestrator.run_event(req.event_type, req.payload)
        run.status = "SUCCEEDED"
        run.created_count = result["created_count"]
        run.details = str(result)
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
        return result | {"run_id": run.id}
    except Exception as exc:
        run.status = "FAILED"
        run.details = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
        raise HTTPException(status_code=500, detail="Agent event processing failed") from exc


@app.post("/api/strategy/recommend")
async def recommend_strategy(
    req: StrategyRequest,
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    return ContentStrategyService().recommend(req.focus)


@app.post("/api/research/discover")
async def research_discover(
    req: ResearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    try:
        opportunities = await ResearchService(session).research_and_rank(
            profile_id=int(current_user.id),
            requested_topic=req.topic,
            candidate_limit=10,
        )
        return {"opportunities": opportunities}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Live research failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to load. Please try again.") from exc


@app.get("/api/research/opportunities")
async def research_opportunities(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    return {"opportunities": await ResearchService(session).list_opportunities(int(current_user.id), 10)}


@app.post("/api/research/evidence")
async def build_research_evidence(
    req: ResearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    return ResearchService(session).build_evidence_pack(
        req.topic or "",
        req.sources,
    )


@app.delete("/api/learning/thoughts")
async def delete_learning_thoughts(
    req: LearningThoughtDeleteRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    if len(req.ids) > 50:
        raise HTTPException(status_code=400, detail="You can delete at most 50 personal insights at once.")
    profile = await AuthService.get_or_create_profile(session, current_user)
    deleted = await BrandLearningService(session).delete_manual_thoughts(
        int(profile.id),
        req.ids,
    )
    return {"deleted": deleted}


@app.get("/api/learning/thoughts")
async def learning_thoughts(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)
    result = await session.execute(
        select(LearningEvent)
        .where(
            LearningEvent.profile_id == profile.id,
            LearningEvent.event_type == "USER_THOUGHT",
            LearningEvent.source_type == "manual_thought",
            LearningEvent.status != "DELETED",
        )
        .order_by(LearningEvent.created_at.desc())
        .limit(50)
    )
    thoughts = []
    for event in result.scalars().all():
        metadata = {}
        try:
            metadata = json.loads(event.metadata_json or "{}")
        except (TypeError, ValueError):
            metadata = {}
        thoughts.append({
            "id": int(event.id),
            "content": event.content,
            "title": str(metadata.get("title") or "").strip() or None,
            "topic": str(metadata.get("topic") or "").strip() or None,
            "status": event.status,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        })
    return {"thoughts": thoughts}


@app.post("/api/learning/thought")
async def save_learning_thought(req: LearningThoughtRequest, session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user"))):
    content = (req.content or "").strip()
    if len(content) < 10:
        raise HTTPException(status_code=400, detail="Write a little more so Suvacya has a useful idea to learn from.")
    if len(content) > 20000:
        raise HTTPException(status_code=400, detail="Thoughts are limited to 20,000 characters.")
    profile = await AuthService.get_or_create_profile(session, current_user)
    event_id = await BrandLearningService(session).record_event(
        profile_id=profile.id,
        event_type="USER_THOUGHT",
        source_type="manual_thought",
        content=content,
        metadata={"topic": (req.topic or "").strip()[:300], "title": (req.title or "").strip()[:200]},
    )
    await session.commit()
    return {"saved": True, "event_id": event_id}


@app.get("/api/learning/status")
async def learning_status(session: AsyncSession = Depends(get_session), current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user"))):
    profile = await AuthService.get_or_create_profile(session, current_user)
    return await BrandLearningService(session).summary(profile.id)


@app.post("/api/voice/profile")
async def build_voice_profile(
    req: VoiceRequest,
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    return VoiceProfileBuilder().learn(req.approved_examples)


@app.post("/api/content/improve")
async def improve_content(
    req: ImproveContentRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="Enter a draft before asking Suvacya to improve it.")
    profile = await AuthService.get_or_create_profile(session, current_user)
    if profile is None:
        raise HTTPException(status_code=400, detail="Complete Brand DNA setup first.")
    if (
        not profile.professional_title
        or not profile.industry
        or not profile.tone
    ):
        raise HTTPException(status_code=400, detail="Complete Professional Title, Industry and Desired Tone before improving content.")

    brand_service = BrandIntelligenceService(session)
    memory = await brand_service.get_memory(profile.id)
    if memory is None or memory.status != "READY":
        raise HTTPException(status_code=400, detail="Complete Brand Intelligence setup first.")

    # Polishing stays fast and uses the saved Brand DNA plus relevant learning memory.
    # Interactive polish should never wait on the embedding/semantic-search path.
    # Recent learning memory and Brand DNA are enough to polish a user draft quickly.
    brand_context = await brand_service.generation_context(profile.id, query=None)
    voice_result = await session.execute(
        select(VoiceMemory).where(VoiceMemory.profile_id == profile.id).limit(1)
    )
    voice = voice_result.scalar_one_or_none()
    voice_context = {
        "tone": voice.tone if voice else profile.tone,
        "sentence_style": voice.sentence_style if voice else "clear and grounded",
        "preferred_phrases": voice.preferred_phrases if voice else "",
        "avoid_phrases": voice.avoid_phrases if voice else "",
        "technical_depth": voice.technical_depth if voice else "moderate",
    }

    system = """You are the polishing editor inside a human-controlled LinkedIn personal-brand product.
Improve the user's own draft without changing what they mean.

Rules:
- Preserve the user's facts, intent, language and personal claims. Never invent experience, metrics, credentials, clients or opinions.
- If the draft is in Hindi, Hinglish or another language, keep that language unless a change is necessary for clarity.
- Improve hook, structure, readability, specificity and professional tone.
- Remove filler, generic AI language and repetition.
- Do not make the post sound artificially corporate.
- Do not add unsupported facts.
- Never use em dashes, en dashes or semicolons.
- Prefer ordinary human wording, natural sentence lengths and concrete language.
- Avoid polished corporate filler, generic AI hooks and phrases that sound machine-written.
- Return JSON only:
{"title":"","topic":"","body":"","changes":[""],"claims":[{"text":"","support":"user_draft"}]}
"""
    prompt = json.dumps({
        "profile": {
            "title": profile.professional_title,
            "industry": profile.industry,
            "experience_years": profile.experience_years,
            "tone": profile.tone,
        },
        "brand_intelligence": brand_context,
        "voice": voice_context,
        "user_language": req.language,
        "title": req.title,
        "topic": req.topic,
        "draft": req.body,
    }, ensure_ascii=False)

    try:
        improved = await ModelRouterService().generate_json(system, prompt, max_output_tokens=1000)
        fallback_used = False
    except Exception as exc:
        # Keep the editor usable during free-tier provider throttling/outages.
        # The fallback never invents content. It only normalizes the user's own draft.
        logger.warning("Content improvement provider unavailable, using safe local fallback: %s", exc)
        improved = {
            "title": req.title,
            "topic": req.topic,
            "body": req.body,
            "changes": ["Cleaned spacing and paragraph structure while preserving your wording."],
            "claims": [],
        }
        fallback_used = True

    body = normalize_human_style(str(improved.get("body") or ""))
    if not body:
        raise HTTPException(status_code=502, detail="The configured LLM provider returned an empty polished draft.")
    guard = run_content_guards(body)
    return {
        "title": str(improved.get("title") or req.title).strip(),
        "topic": str(improved.get("topic") or req.topic).strip(),
        "body": body,
        "changes": improved.get("changes") or [],
        "claims": improved.get("claims") or [],
        "fallback_used": fallback_used,
        "guard": guard.__dict__,
    }


@app.get("/api/analytics/overview")
async def analytics_overview(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile_id = int(current_user.id)
    historical_result = await session.execute(
        select(func.count(HistoricalPost.id)).where(HistoricalPost.profile_id == profile_id)
    )
    content_result = await session.execute(
        select(func.count(ContentItem.id)).where(ContentItem.profile_id == profile_id)
    )
    approval_counts_result = await session.execute(
        select(ApprovalRequest.status, func.count(ApprovalRequest.id))
        .join(ContentVersion, ContentVersion.id == ApprovalRequest.content_version_id)
        .join(ContentItem, ContentItem.id == ContentVersion.content_id)
        .where(ContentItem.profile_id == profile_id)
        .group_by(ApprovalRequest.status)
    )
    approval_counts = {str(status): int(count) for status, count in approval_counts_result.all()}
    pipeline = {
        "historical_posts": int(historical_result.scalar_one() or 0),
        "content_items": int(content_result.scalar_one() or 0),
        "pending_approval": sum(approval_counts.get(status, 0) for status in ("PENDING", "EDITED", "REGENERATED")),
        "approved": approval_counts.get("APPROVED", 0),
        "published_via_brand_os": approval_counts.get("EXECUTED", 0),
    }

    if not settings.linkedin_analytics_oauth_enabled:
        return {
            "pipeline": pipeline,
            "linkedin_performance": {
                "available": False,
                "authorization_required": False,
                "message": "LinkedIn performance analytics will appear when the required LinkedIn analytics access is enabled.",
            },
        }

    user = current_user

    connection_result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == int(user.id))
    )
    connection = connection_result.scalar_one_or_none()

    if connection is None:
        return {
            "pipeline": pipeline,
            "linkedin_performance": {
                "available": False,
                "authorization_required": True,
                "message": "Connect LinkedIn first. Analytics requires the official Community Management member analytics permissions.",
            },
        }

    if connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc):
        return {
            "pipeline": pipeline,
            "linkedin_performance": {
                "available": False,
                "authorization_required": True,
                "message": "Your LinkedIn connection has expired. Reconnect after analytics permissions are enabled.",
            },
        }

    try:
        linkedin_token, token_encrypted = decrypt_linkedin_token(connection.access_token)
        if not token_encrypted:
            connection.access_token = encrypt_linkedin_token(linkedin_token)
            await session.commit()
        linkedin_performance = await LinkedInAnalyticsService(linkedin_token).fetch(days=30)
    except Exception as exc:
        detail = str(exc)
        if "HTTP 401" in detail or "HTTP 403" in detail:
            linkedin_performance = {
                "available": False,
                "authorization_required": True,
                "message": "LinkedIn analytics access is not enabled for this connection yet. Reconnect after LinkedIn grants the required analytics permissions.",
            }
        else:
            logger.exception("LinkedIn analytics failed: %s", exc)
            linkedin_performance = {
                "available": False,
                "authorization_required": False,
                "message": "LinkedIn analytics is temporarily unavailable. Refresh the Analytics section and try again.",
            }

    return {"pipeline": pipeline, "linkedin_performance": linkedin_performance}


@app.post("/api/content/drafts")
async def create_draft(
    req: DraftRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)
    if (
        not profile.professional_title
        or not profile.industry
        or not profile.tone
    ):
        raise HTTPException(status_code=400, detail="Complete Professional Title, Industry and Desired Tone before creating content.")
    brand_memory = await BrandIntelligenceService(session).get_memory(profile.id)
    if brand_memory is None or brand_memory.status != "READY":
        raise HTTPException(status_code=400, detail="Complete Brand DNA setup before creating content.")

    guard = run_content_guards(req.body)
    digest = hashlib.sha256(req.body.strip().encode("utf-8")).hexdigest()
    existing_content = await session.execute(
        select(ContentVersion.id)
        .join(ContentItem, ContentItem.id == ContentVersion.content_id)
        .where(
            ContentItem.profile_id == profile.id,
            ContentVersion.content_hash == digest,
        )
        .limit(1)
    )
    if existing_content.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This exact content already exists in your brand memory.")

    existing_historical = await session.execute(
        select(HistoricalPost.id).where(
            HistoricalPost.profile_id == profile.id,
            HistoricalPost.content_hash == digest,
        ).limit(1)
    )
    if existing_historical.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This exact content already exists in your brand memory.")

    item = ContentItem(
        profile_id=profile.id,
        title=req.title,
        topic=req.topic,
        pillar=req.pillar,
        status="AWAITING_APPROVAL" if guard.passed else "EDIT_REQUIRED",
    )
    session.add(item)
    await session.flush()

    digest = hashlib.sha256(req.body.encode("utf-8")).hexdigest()
    version = ContentVersion(content_id=item.id, body=req.body, content_hash=digest)
    session.add(version)
    await session.commit()
    await session.refresh(version)

    await BrandLearningService(session).record_event(
        profile_id=profile.id,
        event_type="CONTENT_DRAFT",
        source_type="manual_content",
        source_id=version.id,
        content=req.body,
        metadata={"title": req.title, "topic": req.topic, "guard_passed": guard.passed},
    )
    await session.commit()

    approval = None
    if guard.passed:
        approval = await ApprovalService(session).request(version)

    return {
        "content_id": item.id,
        "version_id": version.id,
        "guard": guard.__dict__,
        "approval_id": approval.id if approval else None,
    }


@app.post("/api/approvals/{approval_id}/approve")
async def approve(
    approval_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    try:
        approval = await ApprovalService(session).approve(approval_id, int(current_user.id))
        return {
            "id": approval.id,
            "status": approval.status,
            "approval_hash": approval.approval_hash,
            "approved_at": approval.approved_at,
            "message": "Approved. The content is now locked and ready for execution.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/execute")
async def execute_approval(
    approval_id: int,
    image: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    try:
        connection_result = await session.execute(
            select(LinkedInConnection).where(LinkedInConnection.user_id == int(current_user.id))
        )
        connection = connection_result.scalar_one_or_none()
        if connection is None:
            raise ValueError("Connect your LinkedIn account before executing the post.")
        if connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc):
            raise ValueError("Your LinkedIn connection has expired. Reconnect LinkedIn before executing the post.")

        image_bytes = None
        image_mime = None
        if image is not None:
            image_mime = (image.content_type or "").lower()
            if image_mime not in {"image/jpeg", "image/png", "image/gif"}:
                raise ValueError("Only JPEG or PNG images are supported.")
            image_bytes = await image.read()
            if not image_bytes:
                raise ValueError("The selected image is empty.")
            if len(image_bytes) > 4 * 1024 * 1024:
                raise ValueError("Image must be 4 MB or smaller.")

        linkedin_token, token_encrypted = decrypt_linkedin_token(connection.access_token)
        if not token_encrypted:
            from app.services.security import encrypt_linkedin_token
            connection.access_token = encrypt_linkedin_token(linkedin_token)
            await session.commit()
        publish_adapter = OfficialLinkedInAdapter(linkedin_token, connection.member_sub)
        publish_result = await ApprovalService(session).execute(
            approval_id,
            publish_adapter,
            int(current_user.id),
            image_bytes=image_bytes,
            image_mime=image_mime,
        )
        # Return a durable publication confirmation so the UI can render
        # success without inferring it from a transient HTTP response.
        result = await session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
        )
        saved_approval = result.scalar_one_or_none()
        return {
            "id": approval_id,
            "status": "EXECUTED" if publish_result.success else "APPROVED",
            "published": publish_result.success,
            "external_id": publish_result.external_id,
            "image_urn": getattr(publish_result, "image_urn", None),
            "published_at": saved_approval.published_at if saved_approval else None,
            "message": publish_result.message,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/approvals/{approval_id}/publication")
async def publication_confirmation(
    approval_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    """Return the durable publication result for a user-owned approval."""
    result = await session.execute(
        select(ApprovalRequest)
        .join(ContentVersion, ContentVersion.id == ApprovalRequest.content_version_id)
        .join(ContentItem, ContentItem.id == ContentVersion.content_id)
        .where(
            ApprovalRequest.id == approval_id,
            ContentItem.profile_id == int(current_user.id),
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")

    return {
        "id": approval.id,
        "status": approval.status,
        "published": approval.status == "EXECUTED",
        "external_id": approval.published_external_id,
        "image_urn": approval.published_image_urn,
        "published_at": approval.published_at,
        "message": (
            "Published to LinkedIn."
            if approval.status == "EXECUTED"
            else "This post has not been published to LinkedIn."
        ),
    }


@app.post("/api/approvals/{approval_id}/edit")
async def edit_approval(
    approval_id: int,
    req: ApprovalEditRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    try:
        approval = await ApprovalService(session).edit(approval_id, req.edited_body, req.reason, int(current_user.id))
        return {
            "id": approval.id,
            "status": approval.status,
            "reason": approval.reason,
            "edited_body": approval.edited_body,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/reject")
async def reject_approval(
    approval_id: int,
    req: ApprovalDecisionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    try:
        approval = await ApprovalService(session).reject(approval_id, req.reason, int(current_user.id))
        return {
            "id": approval.id,
            "status": approval.status,
            "reason": approval.reason,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/regenerate")
async def regenerate_approval(
    approval_id: int,
    req: ApprovalDecisionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    try:
        approval = await ApprovalService(session).regenerate(approval_id, req.reason, int(current_user.id))
        return {
            "id": approval.id,
            "status": approval.status,
            "reason": approval.reason,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
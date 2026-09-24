import hashlib
import json
import logging
import os
import sqlite3
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.research import ResearchService
from app.agents.orchestrator import AgentOrchestrator
from app.agents.strategy import ContentStrategyService
from app.agents.voice import VoiceProfileBuilder
from app.auth import require_roles
from app.core.config import settings
from app.db.database import engine, get_session, SessionLocal
from app.services.agent_scheduler import AgentScheduler
from app.services.brand_intelligence import BrandIntelligenceService
from app.guards.guardrails import normalize_human_style, run_content_guards
from app.integrations.linkedin import OfficialLinkedInAdapter
from app.models.base import Base
from app.models.models import ApprovalRequest, ContentItem, ContentVersion, HistoricalPost, LinkedInConnection, UserProfile, VoiceMemory, AgentRun, AuthSession
from app.services.approval import ApprovalService
from app.services.auth_service import AppUser, AuthService
from app.services.linkedin_oauth import build_authorization_url, exchange_code, handle_callback, sync_linkedin_profile
from app.services.linkedin_analytics import LinkedInAnalyticsService
from app.services.gemini_service import ModelRouterService

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
    absolute_path = _resolve_sqlite_path()
    if _database_needs_reset() and absolute_path and os.path.exists(absolute_path):
        os.remove(absolute_path)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    agent_scheduler.start()
    yield
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

    goal: str
    audience: str


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str | None = None
    audience: str | None = None
    sources: list[dict[str, str]] = Field(default_factory=list)


class VoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_examples: list[str]


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = "User"
    professional_title: str | None = None
    industry: str | None = None
    audience: str | None = None
    goals: list[str] | None = None
    brand_positioning: str | None = None
    tone: str | None = None


class BrandOnboardingPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    published_at: str | None = None
    external_id: str | None = None
    metadata: dict[str, object] = {}


class BrandOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = "User"
    professional_title: str | None = None
    industry: str | None = None
    audience: str | None = None
    goals: list[str] = Field(default_factory=list)
    brand_positioning: str | None = None
    tone: str | None = None
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


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "external_actions": "approval_required",
        "agent_enabled": settings.agent_enabled,
        "agent_modes": ["daily_discovery", "event_driven", "scheduled_calendar"],
    }


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
        secure=bool(settings.is_production),
        samesite="lax",
        path="/api/auth/linkedin",
    )
    return response


@app.get("/api/auth/linkedin/callback")
async def linkedin_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    if error:
        response = RedirectResponse(
            url=f"{(settings.frontend_url or 'http://localhost:3000').rstrip('/')}/?linkedin_error=authorization_denied",
            status_code=302,
        )
        response.delete_cookie("brand_os_oauth_state", path="/api/auth/linkedin")
        return response
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing LinkedIn OAuth code or state.")

    expected_state = request.cookies.get("brand_os_oauth_state")
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Invalid LinkedIn OAuth state.")

    browser_nonce = state.split(".", 1)[0] if "." in state else None
    exchange = await handle_callback(session, code, state)
    frontend = (settings.frontend_url or "http://localhost:3000").rstrip("/")
    nonce_suffix = f"&oauth_nonce={browser_nonce}" if browser_nonce else ""
    response = RedirectResponse(url=f"{frontend}/?linkedin_code={exchange}{nonce_suffix}", status_code=302)
    response.delete_cookie("brand_os_oauth_state", path="/api/auth/linkedin")
    return response


@app.post("/api/auth/linkedin/exchange")
async def linkedin_oauth_exchange(
    req: LinkedInExchangeRequest,
    session: AsyncSession = Depends(get_session),
):
    return await exchange_code(session, req.code)


@app.post("/api/linkedin/sync-profile")
async def linkedin_sync_profile(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    user = await AuthService.get_user_from_token(session, credentials.credentials if credentials else None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await sync_linkedin_profile(session, int(user.id))


@app.get("/api/linkedin/status")
async def linkedin_status(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    user = await AuthService.get_user_from_token(session, credentials.credentials if credentials else None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    result = await session.execute(
        select(LinkedInConnection).where(LinkedInConnection.user_id == int(user.id))
    )
    connection = result.scalar_one_or_none()
    return {
        "connected": connection is not None,
        "name": connection.linkedin_name if connection else None,
        "email": connection.linkedin_email if connection else None,
        "expires_at": connection.token_expires_at if connection else None,
    }


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
    token = credentials.credentials if credentials else None
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
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
):
    token = credentials.credentials if credentials else None
    if token:
        token_hash = AuthService.hash_token(token)
        result = await session.execute(select(AuthSession).where(AuthSession.token_hash == token_hash))
        session_row = result.scalar_one_or_none()
        if session_row is not None:
            await session.delete(session_row)
            await session.commit()
    return {"success": True}

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
        "audience": profile.audience,
        "brand_positioning": profile.brand_positioning,
        "tone": profile.tone,
        "role": profile.role or "owner",
    }


@app.post("/api/profile")
async def upsert_profile_legacy():
    raise HTTPException(
        status_code=410,
        detail="Manual profile editing is disabled. LinkedIn is the factual profile source.",
    )


@app.get("/api/brand/status")
async def brand_status(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    service = BrandIntelligenceService(session)
    profile = await AuthService.get_or_create_profile(session, current_user)
    await session.commit()
    memory = await service.get_memory(profile.id)
    posts = await service.get_posts(profile.id, limit=100)
    return {
        "status": memory.status if memory else "NOT_INITIALIZED",
        "ready": bool(memory and memory.status == "READY"),
        "source_post_count": memory.source_post_count if memory else len(posts),
        "current_post_count": len(posts),
        "summary": memory.summary if memory else None,
        "continuous_learning": True,
        "historical_import_optional": True,
        "last_updated": memory.updated_at if memory else None,
        "profile": {
            "display_name": profile.display_name if profile else "User",
            "professional_title": profile.professional_title if profile else None,
            "industry": profile.industry if profile else None,
            "audience": profile.audience if profile else None,
            "brand_positioning": profile.brand_positioning if profile else None,
            "tone": profile.tone if profile else None,
            "goals": (profile.goals.split(",") if profile and profile.goals else []),
        },
        "source_posts": [
            {"id": post.id, "body": post.body, "published_at": post.published_at, "source": post.source}
            for post in posts
            if post.source == "user_import"
        ][:10],
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
    result = await session.execute(
        select(HistoricalPost)
        .where(HistoricalPost.profile_id == int(current_user.id), HistoricalPost.source == "user_import")
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

    if len(req.posts) < 3:
        raise HTTPException(status_code=400, detail="At least 3 previous posts are required to build Brand Intelligence.")
    if len(req.posts) > 10:
        raise HTTPException(status_code=400, detail="You can import a maximum of 10 previous posts.")
    if any(not post.body.strip() for post in req.posts):
        raise HTTPException(status_code=400, detail="Every imported post must contain content.")

    profile = await AuthService.get_or_create_profile(session, current_user)

    # LinkedIn is the factual profile source. Imported posts are the only
    # user-controlled onboarding input.
    profile.display_name = current_user.display_name or profile.display_name or "User"
    profile.role = profile.role or current_user.role or "user"
    await session.commit()

    # The editable 3–10 source posts are a current snapshot. Replace only the
    # user-imported set on refresh; keep Brand OS published posts as durable evidence.
    await session.execute(
        delete(HistoricalPost).where(
            HistoricalPost.profile_id == int(current_user.id),
            HistoricalPost.source == "user_import",
        )
    )
    await session.commit()

    service = BrandIntelligenceService(session)
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
async def brand_initialize(
    req: ProfileRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "user")),
):
    profile = await AuthService.get_or_create_profile(session, current_user)

    # Do not trust client-supplied profile facts. LinkedIn remains the factual
    # baseline and Brand Intelligence derives the remaining signals.
    profile.display_name = current_user.display_name or profile.display_name or "User"
    profile.role = profile.role or current_user.role or "user"

    # A no-post initialization is an explicit request to remove the current
    # user-imported source snapshot. Published Brand OS evidence is preserved.
    await session.execute(
        delete(HistoricalPost).where(
            HistoricalPost.profile_id == profile.id,
            HistoricalPost.source == "user_import",
        )
    )

    try:
        memory = await BrandIntelligenceService(session).analyze(profile.id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Brand Intelligence initialization failed. Check the configured LLM providers and try again.") from exc

    return {"brand_memory": memory}


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
    approvals = await ApprovalService(session).list_dashboard(int(current_user.id))
    records = []
    for item in approvals:
        version = await session.get(ContentVersion, item.content_version_id)
        content_item = await session.get(ContentItem, version.content_id) if version else None
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
    return {"pending_approvals": records}


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
    payload: dict[str, object] = {}


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
    return ContentStrategyService().recommend(req.goal, req.audience)


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
            candidate_limit=8,
        )
        return {"opportunities": opportunities}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Live research failed: %s", exc)
        raise HTTPException(status_code=502, detail="Live research failed. The public source feed or configured LLM provider was unavailable. Please try again.") from exc


@app.get("/api/research/opportunities")
async def research_opportunities(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    return {"opportunities": await ResearchService(session).list_opportunities(int(current_user.id), 20)}


@app.post("/api/research/evidence")
async def build_research_evidence(
    req: ResearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    return ResearchService(session).build_evidence_pack(
        req.topic or "",
        req.audience or "",
        req.sources,
    )


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
        raise HTTPException(status_code=400, detail="Enter a draft before asking Brand OS to improve it.")
    profile = await AuthService.get_or_create_profile(session, current_user)
    if profile is None:
        raise HTTPException(status_code=400, detail="Complete Brand Intelligence setup first.")

    brand_service = BrandIntelligenceService(session)
    memory = await brand_service.get_memory(profile.id)
    if memory is None or memory.status != "READY":
        raise HTTPException(status_code=400, detail="Complete Brand Intelligence setup first.")

    # Polishing should not trigger a hidden Brand DNA re-analysis. The user's
    # saved Brand DNA is the source of truth and the editor should stay fast.
    recent_posts = await brand_service.get_posts(profile.id, limit=3)
    brand_context = {
        "brand_memory": brand_service.serialize(memory),
        "historical_examples": [
            {
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "source": post.source,
                "body": post.body[:1200],
            }
            for post in recent_posts
        ],
    }
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
            "audience": profile.audience,
            "positioning": profile.brand_positioning,
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
    except Exception as exc:
        logger.exception("Content improvement failed: %s", exc)
        raise HTTPException(status_code=502, detail="Content improvement failed. Please try again.") from exc

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
        "guard": guard.__dict__,
    }


@app.get("/api/analytics/overview")
async def analytics_overview(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    current_user: AppUser = Depends(require_roles("admin", "owner", "reviewer", "user")),
):
    async def count(query):
        return len((await session.execute(query)).scalars().all())

    pipeline = {
        "historical_posts": await count(select(HistoricalPost.id).where(HistoricalPost.profile_id == int(current_user.id))),
        "content_items": await count(select(ContentItem.id).where(ContentItem.profile_id == int(current_user.id))),
        "pending_approval": await count(select(ApprovalRequest.id).join(ContentVersion, ContentVersion.id == ApprovalRequest.content_version_id).join(ContentItem, ContentItem.id == ContentVersion.content_id).where(ContentItem.profile_id == int(current_user.id), ApprovalRequest.status.in_(["PENDING", "EDITED", "REGENERATED"]))),
        "approved": await count(select(ApprovalRequest.id).join(ContentVersion, ContentVersion.id == ApprovalRequest.content_version_id).join(ContentItem, ContentItem.id == ContentVersion.content_id).where(ContentItem.profile_id == int(current_user.id), ApprovalRequest.status == "APPROVED")),
        "published_via_brand_os": await count(select(ApprovalRequest.id).join(ContentVersion, ContentVersion.id == ApprovalRequest.content_version_id).join(ContentItem, ContentItem.id == ContentVersion.content_id).where(ContentItem.profile_id == int(current_user.id), ApprovalRequest.status == "EXECUTED")),
    }

    user = await AuthService.get_user_from_token(session, credentials.credentials if credentials else None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

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
        linkedin_performance = await LinkedInAnalyticsService(connection.access_token).fetch(days=30)
    except Exception as exc:
        detail = str(exc)
        if "HTTP 401" in detail or "HTTP 403" in detail:
            linkedin_performance = {
                "available": False,
                "authorization_required": True,
                "message": "LinkedIn analytics access is not enabled for this connection yet. The app needs r_member_postAnalytics, and r_member_profileAnalytics if follower trends are enabled. After LinkedIn grants the permissions, reconnect the account so the new consent is included.",
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
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "reviewer", "owner", "user")),
):
    try:
        existing = await session.get(ApprovalRequest, approval_id)
        if existing and existing.status == "APPROVED":
            approval = await ApprovalService(session)._get_owned_approval(approval_id, int(current_user.id))
        else:
            approval = await ApprovalService(session).approve(approval_id, int(current_user.id))

        # Approval is the explicit human authorization. Once granted, publish
        # immediately through the connected official LinkedIn API so the UI
        # action has one unambiguous outcome: Approve & publish.
        connection_result = await session.execute(
            select(LinkedInConnection).where(LinkedInConnection.user_id == int(current_user.id))
        )
        connection = connection_result.scalar_one_or_none()
        if connection is None:
            raise ValueError("Connect your LinkedIn account before approving for publication.")
        if connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc):
            raise ValueError("Your LinkedIn connection has expired. Reconnect LinkedIn before approving for publication.")

        publish_adapter = OfficialLinkedInAdapter(connection.access_token, connection.member_sub)
        publish_result = await ApprovalService(session).execute(approval_id, publish_adapter, int(current_user.id))
        return {
            "id": approval.id,
            "status": "EXECUTED" if publish_result.success else approval.status,
            "approval_hash": approval.approval_hash,
            "approved_at": approval.approved_at,
            "published": publish_result.success,
            "external_id": publish_result.external_id,
            "message": publish_result.message,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/api/approvals/{approval_id}/execute")
async def execute(
    approval_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(require_roles("admin", "owner", "user")),
):
    try:
        connection_result = await session.execute(
            select(LinkedInConnection).where(LinkedInConnection.user_id == int(current_user.id))
        )
        connection = connection_result.scalar_one_or_none()
        if connection is None:
            raise ValueError("Connect your LinkedIn account before publishing.")
        if connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc):
            raise ValueError("Your LinkedIn connection has expired. Reconnect LinkedIn before publishing.")
        publish_adapter = OfficialLinkedInAdapter(connection.access_token, connection.member_sub)
        result = await ApprovalService(session).execute(approval_id, publish_adapter, int(current_user.id))
        return {
            "success": result.success,
            "external_id": result.external_id,
            "message": result.message,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

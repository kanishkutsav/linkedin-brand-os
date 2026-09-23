import hashlib
import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request\nfrom fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.research import ResearchService
from app.agents.strategy import ContentStrategyService
from app.agents.voice import VoiceProfileBuilder
from app.auth import require_roles
from app.core.config import settings
from app.db.database import engine, get_session
from app.guards.guardrails import run_content_guards
from app.integrations.linkedin import MockLinkedInAdapter, OfficialLinkedInAdapter
from app.models.base import Base
from app.models.models import ContentItem, ContentVersion, LinkedInConnection, UserProfile, VoiceMemory
from app.services.approval import ApprovalService
from app.services.auth_service import AuthService\nfrom app.services.linkedin_oauth import build_authorization_url, exchange_code, handle_callback


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    absolute_path = _resolve_sqlite_path()
    if _database_needs_reset() and absolute_path and os.path.exists(absolute_path):
        os.remove(absolute_path)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
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

adapter = MockLinkedInAdapter()


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    topic: str
    pillar: str = "Expertise"
    body: str


class StrategyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    audience: str


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    audience: str
    sources: list[dict[str, str]] = []


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


class ApprovalEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edited_body: str
    reason: str | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class LinkedInLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    linkedin_url: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "external_actions": "mock_only"}


@app.get("/api/auth/linkedin/start")
async def linkedin_oauth_start(session: AsyncSession = Depends(get_session)):
    url = await build_authorization_url(session)
    return RedirectResponse(url=url, status_code=302)


@app.get("/api/auth/linkedin/callback")
async def linkedin_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if error:
        raise HTTPException(status_code=400, detail=f"LinkedIn authorization was not completed: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing LinkedIn OAuth code or state.")

    exchange = await handle_callback(session, code, state)
    frontend = (settings.frontend_url or "http://localhost:3000").rstrip("/")
    return RedirectResponse(url=f"{frontend}/?linkedin_code={exchange}", status_code=302)


@app.post("/api/auth/linkedin/exchange")
async def linkedin_oauth_exchange(
    code: str,
    session: AsyncSession = Depends(get_session),
):
    return await exchange_code(session, code)


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
async def linkedin_login(req: LinkedInLoginRequest, session: AsyncSession = Depends(get_session)):
    user = await AuthService.validate_linkedin_identity(session, req.email, req.linkedin_url)
    if user is None:
        raise HTTPException(status_code=403, detail="LinkedIn account is not whitelisted for this dashboard")

    token = await AuthService.create_session(session, user)
    return {
        "token": token,
        "role": user.role,
        "email": user.email,
        "display_name": user.display_name,
        "linkedin_url": user.linkedin_url,
    }


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


@app.get("/api/profile")
async def get_profile(session: AsyncSession = Depends(get_session)):
    profile = await session.get(UserProfile, 1)
    if profile is None:
        return {"id": 1, "display_name": "User", "tone": "practical", "role": "owner"}
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
async def upsert_profile(req: ProfileRequest, session: AsyncSession = Depends(get_session)):
    profile = await session.get(UserProfile, 1)
    if profile is None:
        profile = UserProfile(
            id=1,
            display_name=req.display_name,
            professional_title=req.professional_title,
            industry=req.industry,
            audience=req.audience,
            goals=",".join(req.goals or []),
            brand_positioning=req.brand_positioning,
            tone=req.tone,
            role="owner",
        )
        session.add(profile)
    else:
        profile.display_name = req.display_name
        profile.professional_title = req.professional_title
        profile.industry = req.industry
        profile.audience = req.audience
        profile.goals = ",".join(req.goals or [])
        profile.brand_positioning = req.brand_positioning
        profile.tone = req.tone
        profile.role = profile.role or "owner"

    voice = (await session.execute(select(VoiceMemory).limit(1))).scalar_one_or_none()
    if voice is None:
        voice = VoiceMemory(
            profile_id=profile.id,
            tone=req.tone or "practical",
            sentence_style="clear and grounded",
            vocabulary="alignment, execution, clarity",
            preferred_phrases="simple systems, real bottleneck, practical",
            avoid_phrases="game-changer, unlock the power of",
            emoji_usage="limited",
        )
        session.add(voice)

    await session.commit()
    await session.refresh(profile)
    return {"id": profile.id, "display_name": profile.display_name, "tone": profile.tone, "role": profile.role or "owner"}


@app.get("/api/dashboard/approvals")
async def dashboard_approvals(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_roles("admin", "reviewer", "owner")),
):
    approvals = await ApprovalService(session).list_pending()
    pending = []
    for item in approvals:
        version = await session.get(ContentVersion, item.content_version_id)
        pending.append(
            {
                "id": item.id,
                "status": item.status,
                "action_type": item.action_type,
                "reason": item.reason,
                "content": version.body if version else "",
            }
        )
    return {"pending_approvals": pending}


@app.post("/api/strategy/recommend")
async def recommend_strategy(req: StrategyRequest):
    return ContentStrategyService().recommend(req.goal, req.audience)


@app.post("/api/research/evidence")
async def build_research_evidence(req: ResearchRequest):
    return ResearchService().build_evidence_pack(req.topic, req.audience, req.sources)


@app.post("/api/voice/profile")
async def build_voice_profile(req: VoiceRequest):
    return VoiceProfileBuilder().learn(req.approved_examples)


@app.post("/api/content/drafts")
async def create_draft(req: DraftRequest, session: AsyncSession = Depends(get_session)):
    guard = run_content_guards(req.body)
    item = ContentItem(
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
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_roles("admin", "reviewer", "owner")),
):
    try:
        approval = await ApprovalService(session).approve(approval_id)
        return {
            "id": approval.id,
            "status": approval.status,
            "approval_hash": approval.approval_hash,
            "approved_at": approval.approved_at,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/edit")
async def edit_approval(
    approval_id: int,
    req: ApprovalEditRequest,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_roles("admin", "reviewer", "owner")),
):
    try:
        approval = await ApprovalService(session).edit(approval_id, req.edited_body, req.reason)
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
    _: str = Depends(require_roles("admin", "reviewer", "owner")),
):
    try:
        approval = await ApprovalService(session).reject(approval_id, req.reason)
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
    _: str = Depends(require_roles("admin", "reviewer", "owner")),
):
    try:
        approval = await ApprovalService(session).regenerate(approval_id, None)
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
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_roles("admin", "owner")),
):
    try:
        user = await AuthService.get_user_from_token(
            session,
            _.split(":", 1)[1] if isinstance(_, str) and ":" in _ else _,
        )
        if user is None:
            raise ValueError("Authentication required.")

        connection_result = await session.execute(
            select(LinkedInConnection).where(LinkedInConnection.user_id == int(user.id))
        )
        connection = connection_result.scalar_one_or_none()
        publish_adapter = (
            OfficialLinkedInAdapter(connection.access_token, connection.member_sub)
            if connection is not None
            else adapter
        )
        result = await ApprovalService(session).execute(approval_id, publish_adapter)
        return {
            "success": result.success,
            "external_id": result.external_id,
            "message": result.message,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

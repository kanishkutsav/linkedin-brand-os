from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.strategy import ContentStrategyService
from app.agents.voice import VoiceProfileBuilder
from app.core.config import settings
from app.guards.guardrails import run_content_guards
from app.models.models import (
    AuditLog,
    ContentItem,
    ContentVersion,
    FeedbackEntry,
    UserProfile,
    VoiceMemory,
)
from app.services.approval import ApprovalService
from app.services.brand_intelligence import BrandIntelligenceService
from app.services.gemini_service import GeminiService


class AgentOrchestrator:
    """Approval-first content pipeline.

    Gemini may research at a high level, select an angle and draft content.
    It cannot publish, comment, like, DM, connect or otherwise act externally.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _profile(self) -> UserProfile:
        profile = await self.session.get(UserProfile, 1)
        if profile is None:
            profile = UserProfile(
                id=1,
                display_name="User",
                professional_title="Technical Project Manager",
                industry="Technology",
                audience="technology and business leaders",
                goals="Build professional authority",
                brand_positioning="Practical technology, AI, delivery and leadership insights",
                tone="practical, direct, credible",
                role="owner",
            )
            self.session.add(profile)
            await self.session.flush()
        return profile

    async def _voice(self) -> dict:
        memory = (await self.session.execute(select(VoiceMemory).limit(1))).scalar_one_or_none()
        if memory is not None:
            return {
                "tone": memory.tone,
                "sentence_style": memory.sentence_style,
                "vocabulary": memory.vocabulary,
                "preferred_phrases": memory.preferred_phrases,
                "avoid_phrases": memory.avoid_phrases,
                "emoji_usage": memory.emoji_usage,
                "humor_style": memory.humor_style,
                "technical_depth": memory.technical_depth,
                "opinion_style": memory.opinion_style,
                "storytelling_style": memory.storytelling_style,
            }

        result = await self.session.execute(
            select(ContentVersion.body)
            .join(FeedbackEntry, FeedbackEntry.content_version_id == ContentVersion.id)
            .where(FeedbackEntry.action == "APPROVED")
            .limit(10)
        )
        examples = [row[0] for row in result.all()]
        return VoiceProfileBuilder().learn(examples)

    async def _is_duplicate_topic(self, topic: str) -> bool:
        result = await self.session.execute(
            select(ContentItem).where(ContentItem.topic == topic).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _generate_with_gemini(
        self,
        *,
        profile: UserProfile,
        title: str,
        topic: str,
        pillar: str,
        objective: str,
    ) -> dict:
        service = GeminiService()
        brand_context = await BrandIntelligenceService(self.session).generation_context(profile.id)
        return await service.create_post(
            profile={
                "name": profile.display_name,
                "title": profile.professional_title,
                "industry": profile.industry,
                "audience": profile.audience,
                "goals": profile.goals,
                "positioning": profile.brand_positioning,
                "tone": profile.tone,
                "brand_intelligence": brand_context,
            },
            topic=topic,
            pillar=pillar,
            objective=objective,
            evidence=[],
            voice=await self._voice(),
        )

    async def _create_candidate(
        self,
        *,
        title: str,
        topic: str,
        pillar: str,
        objective: str,
        trigger: str,
    ) -> int | None:
        if await self._is_duplicate_topic(topic):
            return None

        profile = await self._profile()
        # Do not produce generic drafts. Every autonomous draft must be grounded
        # in the user's initialized Brand DNA and historical content.
        await BrandIntelligenceService(self.session).generation_context(profile.id)

        generated = None
        if settings.gemini_api_key:
            generated = await self._generate_with_gemini(
                profile=profile,
                title=title,
                topic=topic,
                pillar=pillar,
                objective=objective,
            )

        if generated:
            final_title = str(generated.get("title") or title)[:200]
            body = str(generated.get("body") or "").strip()
            angle = str(generated.get("angle") or "").strip()
            claims = generated.get("claims") or []
            confidence = str(generated.get("confidence") or "medium")
        else:
            final_title = title
            angle = "Focus on the practical tradeoffs behind the topic."
            claims = []
            confidence = "low"
            audience = profile.audience or "professional audience"
            body = (
                f"{title}\n\n"
                f"A practical way to think about {topic.lower()} is to start with the "
                f"business problem, make the workflow explicit, and separate assumptions "
                f"from evidence.\n\n"
                f"For {audience}, three questions are useful:\n"
                f"1. What is the actual bottleneck?\n"
                f"2. Which part can be standardized or automated safely?\n"
                f"3. What should remain under human review?\n\n"
                f"The useful takeaway is not to automate everything. It is to design a "
                f"system where automation handles repeatable work and people retain "
                f"control over decisions that carry meaningful risk."
            )

        if not body:
            raise ValueError("Gemini did not produce a usable draft.")

        guard = run_content_guards(body)
        item = ContentItem(
            title=final_title,
            topic=topic,
            pillar=pillar,
            status="AWAITING_APPROVAL" if guard.passed else "EDIT_REQUIRED",
        )
        self.session.add(item)
        await self.session.flush()

        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        version = ContentVersion(
            content_id=item.id,
            body=body,
            content_hash=digest,
            version_number=1,
        )
        self.session.add(version)
        await self.session.flush()

        metadata = {
            "trigger": trigger,
            "objective": objective,
            "angle": angle,
            "claims": claims,
            "confidence": confidence,
            "generator": "gemini" if generated else "deterministic_fallback",
        }

        if guard.passed:
            approval = await ApprovalService(self.session).request(version)
            self.session.add(
                AuditLog(
                    event_type="AGENT_CANDIDATE_CREATED",
                    actor="agent-orchestrator",
                    payload=json.dumps(
                        {
                            "approval": approval.id,
                            "content": item.id,
                            "topic": topic,
                            "metadata": metadata,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        else:
            self.session.add(
                AuditLog(
                    event_type="AGENT_CANDIDATE_BLOCKED",
                    actor="agent-orchestrator",
                    payload=json.dumps(
                        {
                            "content": item.id,
                            "topic": topic,
                            "issues": guard.issues,
                            "metadata": metadata,
                        },
                        ensure_ascii=False,
                    ),
                )
            )

        await self.session.commit()
        return item.id

    async def run_discovery(self, trigger: str = "scheduled_daily") -> dict:
        profile = await self._profile()
        goal = profile.goals or "professional authority"
        audience = profile.audience or "technology and business leaders"
        strategy = ContentStrategyService().recommend(goal, audience)

        created: list[int] = []
        for idea in strategy["content_calendar"][:3]:
            item_id = await self._create_candidate(
                title=idea["topic"],
                topic=idea["topic"],
                pillar=idea["pillar"],
                objective=idea["objective"],
                trigger=trigger,
            )
            if item_id is not None:
                created.append(item_id)

        return {
            "mode": "discovery",
            "trigger": trigger,
            "created_content_ids": created,
            "created_count": len(created),
        }

    async def run_calendar(self, trigger: str = "scheduled_calendar") -> dict:
        profile = await self._profile()
        goal = profile.goals or "professional authority"
        audience = profile.audience or "technology and business leaders"
        strategy = ContentStrategyService().recommend(goal, audience)

        created: list[int] = []
        for idea in strategy["content_calendar"]:
            item_id = await self._create_candidate(
                title=f"Calendar: {idea['topic']} ({idea['date']})",
                topic=f'{idea["topic"]} — scheduled {idea["date"]}',
                pillar=idea["pillar"],
                objective=idea["objective"],
                trigger=trigger,
            )
            if item_id is not None:
                created.append(item_id)

        return {
            "mode": "calendar",
            "trigger": trigger,
            "created_content_ids": created,
            "created_count": len(created),
        }

    async def run_event(self, event_type: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        profile = await self._profile()
        audience = profile.audience or "technology and business leaders"
        topic = payload.get("topic") or f"Practical lessons from {event_type.replace('_', ' ')}"
        title = payload.get("title") or topic
        pillar = payload.get("pillar") or "Industry insights"
        objective = payload.get("objective") or "Respond to a relevant event"

        item_id = await self._create_candidate(
            title=str(title),
            topic=str(topic),
            pillar=str(pillar),
            objective=str(objective),
            trigger=f"event:{event_type}",
        )
        return {
            "mode": "event",
            "event_type": event_type,
            "audience": audience,
            "created_content_ids": [item_id] if item_id else [],
            "created_count": 1 if item_id else 0,
        }

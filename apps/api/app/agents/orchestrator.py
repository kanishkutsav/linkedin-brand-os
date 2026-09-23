from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.strategy import ContentStrategyService
from app.guards.guardrails import run_content_guards
from app.models.models import AuditLog, ContentItem, ContentVersion, UserProfile, VoiceMemory
from app.services.approval import ApprovalService


class AgentOrchestrator:
    """Coordinates safe, approval-first content discovery and drafting.

    External LinkedIn actions are intentionally out of scope here. The orchestrator
    may create ideas/drafts and approval requests, but only a human-approved
    approval request can reach the LinkedIn action executor.
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

    async def _is_duplicate_topic(self, topic: str) -> bool:
        result = await self.session.execute(
            select(ContentItem).where(ContentItem.topic == topic).limit(1)
        )
        return result.scalar_one_or_none() is not None

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
            f"control over decisions that carry meaningful risk.\n\n"
            f"Objective: {objective}"
        )

        guard = run_content_guards(body)
        item = ContentItem(
            title=title,
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

        if guard.passed:
            approval = await ApprovalService(self.session).request(version)
            self.session.add(
                AuditLog(
                    event_type="AGENT_CANDIDATE_CREATED",
                    actor="agent-orchestrator",
                    payload=f"approval={approval.id};trigger={trigger};topic={topic}",
                )
            )
        else:
            self.session.add(
                AuditLog(
                    event_type="AGENT_CANDIDATE_BLOCKED",
                    actor="agent-orchestrator",
                    payload=f"content={item.id};trigger={trigger};issues={';'.join(guard.issues)}",
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
                title=f"Calendar: {idea['topic']}",
                topic=idea["topic"],
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
            title=title,
            topic=topic,
            pillar=pillar,
            objective=objective,
            trigger=f"event:{event_type}",
        )
        return {
            "mode": "event",
            "event_type": event_type,
            "audience": audience,
            "created_content_ids": [item_id] if item_id else [],
            "created_count": 1 if item_id else 0,
        }

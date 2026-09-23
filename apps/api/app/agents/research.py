from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ContentItem, ContentOpportunity, ResearchSource, UserProfile
from app.services.brand_intelligence import BrandIntelligenceService
from app.services.gemini_service import GeminiService


class ResearchService:
    """Real-time research and evidence discovery using Gemini Google Search grounding."""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def research_and_rank(
        self,
        *,
        profile_id: int = 1,
        requested_topic: str | None = None,
        candidate_limit: int = 8,
    ) -> list[dict]:
        if self.session is None:
            raise ValueError("A database session is required for live research.")

        profile = await self.session.get(UserProfile, profile_id)
        if profile is None:
            raise ValueError("Profile is not initialized.")

        brand = BrandIntelligenceService(self.session)
        context = await brand.generation_context(profile_id)
        historical = await brand.get_posts(profile_id, limit=12)

        recent_content_result = await self.session.execute(
            select(ContentItem.topic, ContentItem.created_at)
            .order_by(ContentItem.created_at.desc())
            .limit(20)
        )
        recent_content = [
            {"topic": row[0], "created_at": row[1].isoformat() if row[1] else None}
            for row in recent_content_result.all()
        ]

        prompt = json.dumps(
            {
                "date": datetime.now(timezone.utc).date().isoformat(),
                "profile": {
                    "title": profile.professional_title,
                    "industry": profile.industry,
                    "audience": profile.audience,
                    "goals": profile.goals,
                    "positioning": profile.brand_positioning,
                },
                "brand_intelligence": context["brand_memory"],
                "recent_historical_posts": [p.body[:1200] for p in historical],
                "recent_content_topics": recent_content,
                "requested_topic": requested_topic,
                "candidate_limit": candidate_limit,
            },
            ensure_ascii=False,
        )

        system = """You are the research and content-opportunity engine for a professional LinkedIn personal-brand system.

Use Google Search grounding to research CURRENT public information. Search broadly enough to identify meaningful developments, but prioritize:
1. primary/official sources,
2. authoritative technical/business sources,
3. reputable reporting when primary sources are unavailable.

The goal is NOT to find random news. Find developments that create a credible reason for THIS person to post.

Hard rules:
- Never invent a personal experience, credential, client, employer, metric or opinion.
- Do not recommend a topic merely because it is trending.
- Prefer topics where the user's documented expertise gives them a useful lens.
- Penalize topics already covered in recent content or historical posts.
- Penalize generic AI hype, motivational content and recycled listicles.
- For time-sensitive claims, require current evidence.
- Distinguish facts from interpretation.
- If evidence is weak or conflicting, lower evidence strength and say so.
- Do not make political persuasion content or infer political preferences.
- Return JSON only.

Return:
{
  "opportunities": [
    {
      "title": "specific opportunity title",
      "topic": "precise topic",
      "angle": "specific point of view the user can credibly take without inventing experience",
      "pillar": "one brand pillar",
      "format": "post format",
      "objective": "why this post exists",
      "why_now": "what changed or why it matters now",
      "evidence_summary": "2-4 factual sentences",
      "source_hints": ["source title or domain"],
      "brand_fit": 0,
      "audience_relevance": 0,
      "timeliness": 0,
      "evidence_strength": 0,
      "novelty": 0,
      "conversation_potential": 0,
      "authenticity": 0,
      "risk": 0,
      "rationale": "why this survived the filter"
    }
  ]
}

Generate 6-8 genuinely different opportunities. Avoid near-duplicates.
"""

        data, grounding = await GeminiService().research_json(system, prompt)
        opportunities = data.get("opportunities") or []
        sources = grounding.get("sources") or []
        queries = grounding.get("queries") or []

        source_records: list[ResearchSource] = []
        for source in sources:
            url = str(source.get("url") or "").strip()
            title = str(source.get("title") or "").strip() or None
            if not url and not title:
                continue
            record = ResearchSource(
                profile_id=profile_id,
                topic=requested_topic or "brand opportunity discovery",
                title=title,
                url=url or None,
                domain=urlparse(url).netloc.lower() or None,
                source_type="google_search_grounding",
                evidence_json=json.dumps({"grounded": True}, ensure_ascii=False),
                search_queries_json=json.dumps(queries, ensure_ascii=False),
                confidence="medium",
            )
            self.session.add(record)
            source_records.append(record)

        await self.session.flush()

        created: list[dict] = []
        for raw in opportunities:
            try:
                scores = {
                    key: max(0.0, min(100.0, float(raw.get(key, 0) or 0)))
                    for key in (
                        "brand_fit",
                        "audience_relevance",
                        "timeliness",
                        "evidence_strength",
                        "novelty",
                        "conversation_potential",
                        "authenticity",
                        "risk",
                    )
                }
                total = (
                    scores["brand_fit"] * 0.22
                    + scores["audience_relevance"] * 0.18
                    + scores["timeliness"] * 0.15
                    + scores["evidence_strength"] * 0.15
                    + scores["novelty"] * 0.12
                    + scores["conversation_potential"] * 0.08
                    + scores["authenticity"] * 0.07
                    - scores["risk"] * 0.03
                )
                if scores["evidence_strength"] < 55 or scores["brand_fit"] < 55:
                    total *= 0.75

                opportunity = ContentOpportunity(
                    profile_id=profile_id,
                    title=str(raw.get("title") or raw.get("topic") or "Untitled opportunity")[:300],
                    topic=str(raw.get("topic") or "")[:500],
                    angle=str(raw.get("angle") or ""),
                    pillar=str(raw.get("pillar") or "Industry insights")[:100],
                    format=str(raw.get("format") or "Insight post")[:100],
                    objective=str(raw.get("objective") or "")[:300],
                    status="RANKED",
                    **scores,
                    total_score=round(total, 2),
                    rationale=str(raw.get("rationale") or ""),
                    research_source_ids_json=json.dumps(
                        [source.id for source in source_records], ensure_ascii=False
                    ),
                    evidence_json=json.dumps(
                        {
                            "why_now": raw.get("why_now"),
                            "summary": raw.get("evidence_summary"),
                            "source_hints": raw.get("source_hints") or [],
                            "grounding_queries": queries,
                        },
                        ensure_ascii=False,
                    ),
                )
                self.session.add(opportunity)
                created.append(
                    {
                        "title": opportunity.title,
                        "topic": opportunity.topic,
                        "angle": opportunity.angle,
                        "pillar": opportunity.pillar,
                        "format": opportunity.format,
                        "objective": opportunity.objective,
                        "total_score": opportunity.total_score,
                        "scores": scores,
                        "rationale": opportunity.rationale,
                        "evidence": json.loads(opportunity.evidence_json or "{}"),
                        "source_ids": [source.id for source in source_records],
                    }
                )
            except (TypeError, ValueError):
                continue

        await self.session.commit()
        created.sort(key=lambda item: item["total_score"], reverse=True)
        return created

    async def list_opportunities(self, profile_id: int = 1, limit: int = 20) -> list[dict]:
        if self.session is None:
            raise ValueError("A database session is required.")
        result = await self.session.execute(
            select(ContentOpportunity)
            .where(ContentOpportunity.profile_id == profile_id)
            .order_by(ContentOpportunity.total_score.desc(), ContentOpportunity.created_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        return [self.serialize(item) for item in result.scalars().all()]

    def serialize(self, item: ContentOpportunity) -> dict:
        return {
            "id": item.id,
            "title": item.title,
            "topic": item.topic,
            "angle": item.angle,
            "pillar": item.pillar,
            "format": item.format,
            "objective": item.objective,
            "status": item.status,
            "total_score": item.total_score,
            "scores": {
                "brand_fit": item.brand_fit,
                "audience_relevance": item.audience_relevance,
                "timeliness": item.timeliness,
                "evidence_strength": item.evidence_strength,
                "novelty": item.novelty,
                "conversation_potential": item.conversation_potential,
                "authenticity": item.authenticity,
                "risk": item.risk,
            },
            "rationale": item.rationale,
            "evidence": json.loads(item.evidence_json or "{}"),
            "source_ids": json.loads(item.research_source_ids_json or "[]"),
            "created_at": item.created_at,
        }

    def build_evidence_pack(self, topic: str, audience: str, sources: list[dict]) -> dict:
        facts = [
            {
                "claim": source.get("summary", "Public source suggests this is relevant."),
                "source_title": source.get("title", "Source"),
                "source_url": source.get("url", ""),
            }
            for source in sources
        ]
        return {
            "topic": topic,
            "audience": audience,
            "facts": facts,
            "sources": sources,
            "confidence": "medium",
            "notes": "Use only as supporting context; validate claims before publishing.",
        }
